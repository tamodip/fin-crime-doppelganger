#!/usr/bin/env python3
"""Local, read-only audit-trail viewer for Track 2 predictions."""
import argparse
import json
import os
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import screen


def read_output(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class Viewer:
    def __init__(self, data_path, output_path):
        self.data = screen.Data(data_path)
        self.output_path = output_path
        self.rows = read_output(output_path)
        self.row_by_hit = {row["hit_id"]: row for row in self.rows}
        self.alert_by_id = {row["alert_id"]: row for row in self.data.alerts}
        self.check_by_id = {}
        for checks in self.data.kyc_by_app.values():
            for check in checks:
                self.check_by_id[check["check_id"]] = check
        self.note_by_id = {}
        for notes in self.data.notes_by_email.values():
            for note in notes:
                self.note_by_id[note["note_id"]] = note
        self.search_by_id = {}
        for results in self.data.search_by_query.values():
            for result in results:
                self.search_by_id[result["result_id"]] = result
        self.account_by_id = {key: values for key, values in self.data.acc_by_id.items()}
        self.groups_by_alert = {}
        for alert in self.data.alerts:
            self.groups_by_alert[alert["alert_id"]] = screen.resolve_customer(self.data, alert)

    def summary(self):
        decisions = Counter(row.get("decision", "REVIEW") for row in self.rows)
        reasons = Counter(row.get("reason_code", "INSUFFICIENT_DATA") for row in self.rows)
        return {
            "hits": len(self.rows),
            "alerts": len(self.data.alerts),
            "decisions": {key: decisions[key] for key in ("DIFFERENT_ENTITY", "SAME_ENTITY", "REVIEW")},
            "reason_codes": dict(sorted(reasons.items())),
        }

    def hit_list(self, query="", decision="ALL", limit=160):
        needle = query.strip().casefold()
        out = []
        for row in self.rows:
            if decision != "ALL" and row.get("decision") != decision:
                continue
            alert = self.alert_by_id.get(row.get("alert_id"), {})
            hit = self.data.hits.get(row.get("hit_id"), {})
            customer = alert.get("customer") or {}
            haystack = " ".join(str(value or "") for value in (
                row.get("hit_id"), row.get("alert_id"), row.get("reason_code"), row.get("reason"),
                hit.get("name"), customer.get("name"), hit.get("position_or_allegation"),
                " ".join(str(x) for x in hit.get("aliases") or []),
            )).casefold()
            if needle and needle not in haystack:
                continue
            out.append({
                "hit_id": row["hit_id"], "alert_id": row["alert_id"],
                "decision": row["decision"], "reason_code": row["reason_code"],
                "customer_name": customer.get("name"), "hit_name": hit.get("name"),
                "category": hit.get("primary_category") or ((hit.get("categories") or [None])[0]),
                "evidence_count": len(row.get("evidence") or []),
                "customer_record_id": row.get("customer_record_id"),
            })
            if len(out) >= limit:
                break
        return out

    def evidence_item(self, identifier, hit):
        if "#" in identifier and identifier.split("#", 1)[0] == hit.get("hit_id"):
            field = identifier.split("#", 1)[1]
            return {"id": identifier, "type": "Hit profile field", "label": field.replace("_", " ").title(),
                    "value": hit.get(field)}
        if identifier in self.data.customers:
            return {"id": identifier, "type": "Customer record", "label": "Customer record", "value": self.data.customers[identifier]}
        if identifier in self.check_by_id:
            check = self.check_by_id[identifier]
            return {"id": identifier, "type": "Identity check", "label": "Approved identity check" if check.get("result") == "approved" else "Excluded identity check", "value": check}
        if identifier in self.note_by_id:
            note = self.note_by_id[identifier]
            return {"id": identifier, "type": "Customer note", "label": note.get("channel", "Note").replace("_", " ").title(), "value": note}
        if identifier in self.search_by_id:
            result = self.search_by_id[identifier]
            return {"id": identifier, "type": "Search result", "label": result.get("source") or result.get("title") or "Search result", "value": result}
        if identifier in self.account_by_id:
            return {"id": identifier, "type": "Account link", "label": "Account", "value": self.account_by_id[identifier]}
        if identifier in self.alert_by_id:
            return {"id": identifier, "type": "Screening alert", "label": "Screening alert", "value": self.alert_by_id[identifier]}
        if identifier in self.data.hits:
            return {"id": identifier, "type": "Watchlist hit", "label": "Hit profile", "value": self.data.hits[identifier]}
        return {"id": identifier, "type": "Reference", "label": "Referenced evidence", "value": None}

    def detail(self, hit_id):
        row = self.row_by_hit.get(hit_id)
        hit = self.data.hits.get(hit_id)
        if row is None or hit is None:
            return None
        alert = self.alert_by_id.get(row["alert_id"], {})
        groups = self.groups_by_alert.get(row["alert_id"], [])
        people = []
        for group in groups:
            person = screen.build_person(self.data, group)
            people.append({
                "records": group,
                "names": person["names"],
                "verified_name": person["verified_name"],
                "verified_source": person["verified_src"],
                "dob": screen.fmt_date(person["dob"]),
                "dob_source": person["dob_src"],
                "countries": sorted(person["countries"]),
                "entity_type": person["entity_type"],
                "country_sources": {country: sorted(sources) for country, sources in person["country_sources"].items()},
            })
        account_refs = []
        if alert.get("account_ref"):
            account_refs = self.data.acc_by_id.get(alert["account_ref"], [])
        elif alert.get("login_handle"):
            account_refs = self.data.acc_by_login.get(alert["login_handle"].lower(), [])
        notes = []
        for group in groups:
            for record_id in group:
                customer = self.data.customers[record_id]
                if customer.get("email"):
                    notes.extend(self.data.notes_by_email.get(customer["email"].lower(), []))
        notes = sorted({n["note_id"]: n for n in notes}.values(), key=lambda n: (n.get("created_at") or "", n["note_id"]))
        checks = []
        for group in groups:
            for record_id in group:
                for applicant in self.data.app_by_cust.get(record_id, ()):
                    checks.extend(self.data.kyc_by_app.get(applicant, ()))
        checks = sorted({c["check_id"]: c for c in checks}.values(), key=lambda c: (c.get("checked_at") or "", c["check_id"]))
        evidence = [self.evidence_item(identifier, hit) for identifier in row.get("evidence") or []]
        facts = {
            "hit_names": screen.hit_names(hit),
            "hit_dobs": [screen.fmt_date(item[2]) if item[2] else " or ".join(str(y) for y in sorted(item[1])) for item in screen.hit_dobs(self.data, hit)],
            "hit_countries": sorted(c for c in screen.hit_countries(hit) if c != "?"),
            "category": hit.get("primary_category") or ((hit.get("categories") or [None])[0]),
            "profile_excerpt": (hit.get("profile_notes") or "").split("\n\n", 1)[0][:900],
        }
        return {
            "output": row, "alert": alert, "hit": hit, "customer_groups": people,
            "accounts": account_refs, "kyc_checks": checks, "customer_notes": notes,
            "hit_facts": facts, "evidence": evidence,
        }


def create_handler(viewer, html_path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Track2Audit/1.0"

        def send_json(self, value, status=200):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/summary":
                return self.send_json(viewer.summary())
            if parsed.path == "/api/hits":
                query = parse_qs(parsed.query)
                return self.send_json(viewer.hit_list(
                    query.get("q", [""])[0], query.get("decision", ["ALL"])[0]))
            if parsed.path.startswith("/api/hit/"):
                hit_id = parsed.path.rsplit("/", 1)[-1]
                detail = viewer.detail(hit_id)
                return self.send_json(detail or {"error": "Hit not found"}, 200 if detail else 404)
            if parsed.path not in ("/", "/index.html"):
                return self.send_json({"error": "Not found"}, 404)
            body = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            sys.stderr.write("audit-ui: " + fmt % args + "\n")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="Track 2 data folder (served locally only)")
    parser.add_argument("--output", required=True, help="JSONL prediction output")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    data_path = os.path.abspath(args.data)
    output_path = os.path.abspath(args.output)
    html_path = Path(__file__).with_name("index.html")
    viewer = Viewer(data_path, output_path)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), create_handler(viewer, html_path))
    print("Track 2 audit viewer: http://127.0.0.1:%d" % args.port)
    print("Reading local data from %s" % data_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping audit viewer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
