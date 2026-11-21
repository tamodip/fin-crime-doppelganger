#!/usr/bin/env python3
"""Metamorphic robustness checks for the screening engine.

Usage: python3 system/stress.py <development data folder> [--report path]
Temporary transformed copies are deleted when the run finishes.
"""
import argparse
import calendar
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import time
from pathlib import Path

import screen


def rows(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_rows(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        for row in data:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def format_partial_date(value):
    parsed = screen.parse_date(value)
    if not parsed:
        return value
    year, month, day = parsed
    if month and day:
        return "%d %s %04d" % (day, calendar.month_name[month], year)
    if month:
        return "%s %04d" % (calendar.month_name[month], year)
    return "%04d" % year


def reformat_dates(text):
    matches = list(screen.dates_in(text or ""))
    result = text or ""
    for pos, raw, parsed in reversed(matches):
        replacement = format_partial_date(raw)
        result = result[:pos] + replacement + result[pos + len(raw):]
    return result


def reverse_name(value):
    if not isinstance(value, str) or not value.strip():
        return value
    # Preserve parenthetical provider annotations: the policy ignores them.
    match = re.match(r"^(.*?)(\s*\([^()]*\))?$", value.strip())
    body, suffix = match.group(1), match.group(2) or ""
    parts = body.replace(",", " ").split()
    if len(parts) < 2:
        return value
    return " ".join(reversed(parts)) + suffix


def normalize_name_surface(value):
    if not isinstance(value, str):
        return value
    text = "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))
    text = text.replace("'", "").replace("’", "")
    return re.sub(r"[^A-Za-z0-9\s]", " ", text).upper()


def country_code_map():
    mapping = {}
    for alias, canonical in screen.COUNTRY_ALIASES.items():
        if len(alias) == 2 and alias.isalpha():
            normalized = screen.norm_country(canonical)
            if normalized:
                mapping.setdefault(normalized, alias.upper())
    return mapping


def code_country(value, mapping):
    if not isinstance(value, str):
        return value, False
    normalized = screen.norm_country(value)
    if normalized in mapping:
        return mapping[normalized], True
    return value, False


def code_address(value, mapping):
    if isinstance(value, dict):
        updated = dict(value)
        changed = False
        for key in ("country", "name"):
            if key in updated:
                updated[key], hit = code_country(updated[key], mapping)
                changed |= hit
                if hit:
                    break
        return updated, changed
    if not isinstance(value, str):
        return value, False
    place, suffix = value, ""
    match = re.match(r"^(.*?)(\s*\[[^]]*\])?$", value)
    place, suffix = match.group(1), match.group(2) or ""
    country = place.rsplit(",", 1)[-1].strip()
    mapped, changed = code_country(country, mapping)
    if not changed:
        return value, False
    prefix = place[:len(place) - len(country)]
    return prefix + mapped + suffix, True


def apply_name_fields(row, fields, transform):
    count = 0
    for field in fields:
        if isinstance(row.get(field), str):
            old = row[field]
            row[field] = transform(old)
            count += row[field] != old
    return count


def transform_dataset(folder, scenario, base_data):
    source = Path(folder)
    temp = tempfile.TemporaryDirectory(prefix="track2-stress-")
    target = Path(temp.name)
    for path in source.iterdir():
        if path.is_file() and (path.suffix == ".jsonl" or path.name == "name_variants.json"):
            shutil.copy2(path, target / path.name)

    counts = {"date strings": 0, "name fields": 0, "country fields": 0, "KYC notes reworded": 0}
    date_mode = scenario in ("date_formats", "combined")
    name_order = scenario in ("name_order", "combined")
    name_surface = scenario in ("name_surface", "combined")
    country_mode = scenario in ("country_codes", "combined")
    note_mode = scenario in ("kyc_note_paraphrase", "combined")
    codes = country_code_map()

    for filename in ("alerts.jsonl", "hits.jsonl", "customers.jsonl", "kyc_checks.jsonl", "notes.jsonl", "search_results.jsonl"):
        path = target / filename
        if not path.exists():
            continue
        data_rows = rows(path)
        for row in data_rows:
            if filename == "alerts.jsonl":
                customer = row.get("customer") or {}
                if name_order:
                    counts["name fields"] += apply_name_fields(customer, ("name",), reverse_name)
                if name_surface:
                    counts["name fields"] += apply_name_fields(customer, ("name",), normalize_name_surface)
                if country_mode and customer.get("country"):
                    customer["country"], changed = code_country(customer["country"], codes)
                    counts["country fields"] += changed
                if date_mode:
                    for key in ("screened_at",):
                        if row.get(key):
                            old = row[key]
                            row[key] = format_partial_date(old)
                            counts["date strings"] += row[key] != old
                    if customer.get("dob"):
                        old = customer["dob"]
                        customer["dob"] = format_partial_date(old)
                        counts["date strings"] += customer["dob"] != old
            elif filename == "customers.jsonl":
                if name_order:
                    counts["name fields"] += apply_name_fields(row, ("full_name", "preferred_name", "login_name"), reverse_name)
                if name_surface:
                    counts["name fields"] += apply_name_fields(row, ("full_name", "preferred_name", "login_name"), normalize_name_surface)
                if country_mode:
                    for key in ("residence_country", "nationality"):
                        if row.get(key):
                            row[key], changed = code_country(row[key], codes)
                            counts["country fields"] += changed
                if date_mode:
                    for key in ("dob",):
                        if row.get(key):
                            old = row[key]
                            row[key] = format_partial_date(old)
                            counts["date strings"] += row[key] != old
            elif filename == "hits.jsonl":
                if name_order:
                    counts["name fields"] += apply_name_fields(row, ("name", "best_matching_name"), reverse_name)
                if name_surface:
                    counts["name fields"] += apply_name_fields(row, ("name", "best_matching_name", "first_name", "middle_name", "last_name"), normalize_name_surface)
                    aliases = row.get("aliases") or []
                    for index, alias in enumerate(aliases):
                        if isinstance(alias, dict) and isinstance(alias.get("name"), str):
                            old = alias["name"]
                            alias["name"] = normalize_name_surface(old)
                            counts["name fields"] += alias["name"] != old
                        elif isinstance(alias, str):
                            aliases[index] = normalize_name_surface(alias)
                if country_mode:
                    for key in ("countries", "nationality", "citizenship"):
                        vals = row.get(key) or []
                        if isinstance(vals, str):
                            vals = [vals]
                        converted = []
                        for value in vals:
                            replacement, changed = code_country(value, codes)
                            converted.append(replacement)
                            counts["country fields"] += changed
                        row[key] = converted
                    for key in ("addresses", "place_of_birth"):
                        values = row.get(key)
                        if isinstance(values, list):
                            updated = []
                            for value in values:
                                replacement, changed = code_address(value, codes)
                                updated.append(replacement)
                                counts["country fields"] += changed
                            row[key] = updated
                        elif values:
                            row[key], changed = code_address(values, codes)
                            counts["country fields"] += changed
                if date_mode:
                    if isinstance(row.get("dobs"), list):
                        updated = []
                        for value in row["dobs"]:
                            replacement = format_partial_date(value)
                            counts["date strings"] += replacement != value
                            updated.append(replacement)
                        row["dobs"] = updated
                    if row.get("deceased_date"):
                        old = row["deceased_date"]
                        row["deceased_date"] = format_partial_date(old)
                        counts["date strings"] += row["deceased_date"] != old
                    if row.get("profile_notes"):
                        old = row["profile_notes"]
                        row["profile_notes"] = reformat_dates(old)
                        counts["date strings"] += row["profile_notes"] != old
            elif filename == "kyc_checks.jsonl":
                if name_order:
                    counts["name fields"] += apply_name_fields(row, ("verified_name",), reverse_name)
                if name_surface:
                    counts["name fields"] += apply_name_fields(row, ("verified_name",), normalize_name_surface)
                if country_mode and row.get("document_country"):
                    row["document_country"], changed = code_country(row["document_country"], codes)
                    counts["country fields"] += changed
                if date_mode:
                    for key in ("checked_at", "verified_dob"):
                        if row.get(key):
                            old = row[key]
                            row[key] = format_partial_date(old)
                            counts["date strings"] += row[key] != old
            elif filename == "notes.jsonl":
                if date_mode:
                    for key in ("created_at",):
                        if row.get(key):
                            old = row[key]
                            row[key] = format_partial_date(old)
                            counts["date strings"] += row[key] != old
                    if row.get("text"):
                        old = row["text"]
                        row["text"] = reformat_dates(old)
                        counts["date strings"] += row["text"] != old
                if note_mode and screen.is_kyc_note(row):
                    name, dob, country = screen.kyc_note_parse(row, base_data)
                    # Only rewrite notes whose original facts were parsed, so the
                    # paraphrase is known to preserve what the baseline consumed.
                    if name and dob and country:
                        row["text"] = "Approved identity check. Legal name: %s; date of birth: %s; identity document country: %s." % (
                            name, format_partial_date(screen.fmt_date(dob)), country)
                        counts["KYC notes reworded"] += 1
            elif filename == "search_results.jsonl" and date_mode:
                if row.get("snippet"):
                    old = row["snippet"]
                    row["snippet"] = reformat_dates(old)
                    counts["date strings"] += row["snippet"] != old
        write_rows(path, data_rows)
    return temp, counts


def compare_outputs(baseline, candidate):
    fields = ("decision", "reason_code", "customer_record_id", "evidence")
    original = {row["hit_id"]: row for row in baseline}
    changed = {row["hit_id"]: row for row in candidate}
    total = len(original)
    stable = {field: sum(original[key].get(field) == changed.get(key, {}).get(field) for key in original) for field in fields}
    differences = []
    policy_drift = 0
    for key in original:
        if any(original[key].get(field) != changed.get(key, {}).get(field)
               for field in ("decision", "reason_code", "customer_record_id")):
            policy_drift += 1
        if any(original[key].get(field) != changed.get(key, {}).get(field) for field in fields):
            differences.append((key, original[key], changed.get(key)))
    return total, stable, differences, policy_drift


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_folder", help="Track 2 data folder; it is read-only")
    parser.add_argument("--report", help="optional path for the aggregate Markdown report")
    parser.add_argument("--scenario", action="append", choices=("date_formats", "name_order", "name_surface", "country_codes", "kyc_note_paraphrase", "combined"),
                        help="run only this scenario; may be repeated (default: all scenarios)")
    args = parser.parse_args()

    base = screen.Data(args.data_folder)
    baseline = screen.evaluate(base)
    scenarios = tuple(args.scenario or ("date_formats", "name_order", "name_surface", "country_codes", "kyc_note_paraphrase", "combined"))
    table_rows = []
    scenario_notes = []
    failures = 0
    for index, scenario in enumerate(scenarios, 1):
        started = time.perf_counter()
        print("[%d/%d] Preparing %s" % (index, len(scenarios), scenario), flush=True)
        temp, counts = transform_dataset(args.data_folder, scenario, base)
        try:
            print("[%d/%d] Evaluating transformed data" % (index, len(scenarios)), flush=True)
            candidate = screen.evaluate(screen.Data(temp.name))
            total, stable, differences, policy_drift = compare_outputs(baseline, candidate)
            failures += policy_drift
            applied = sum(counts.values())
            table_rows.append("| %s | %d | %d/%d | %d/%d | %d/%d | %d/%d |" % (
                scenario, applied, stable["decision"], total, stable["reason_code"], total,
                stable["customer_record_id"], total, stable["evidence"], total))
            evidence_only = len(differences) - policy_drift
            scenario_notes.extend([
                "### " + scenario,
                "",
                "Applied counts: " + ", ".join("%s=%d" % (key, value) for key, value in counts.items()) + ".",
                "Policy-output drift (decision, reason code, or customer resolution): %d hits." % policy_drift,
                "Hits with evidence-ID changes: %d; evidence-only changes: %d." % (total - stable["evidence"], evidence_only),
                "",
            ])
            print("[%d/%d] %s stable on %d/%d hits in %.1fs" % (
                index, len(scenarios), scenario, stable["decision"], total, time.perf_counter() - started), flush=True)
        finally:
            temp.cleanup()
    lines = [
        "# Track 2 metamorphic stress results", "",
        "All transformed copies were temporary and deleted after this run.",
        "The stability figures measure only the listed meaning-preserving transformations; they do not predict the hidden-set score.",
        "Evidence IDs may change when a transformed record expresses the same fact in a different field.", "",
        "| Transformation | Changed inputs | Verdict stable | Reason code stable | Customer resolution stable | Exact evidence IDs stable |",
        "|---|---:|---:|---:|---:|---:|",
    ] + table_rows + ["", "## Scenario details", ""] + scenario_notes + [
        "This report contains aggregate counts only; it does not include the development records or transformed inputs."
    ]
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
