import argparse
import json
import os
import re
import sys

CODES = {
    "TEMPORAL_IMPOSSIBILITY": "DIFFERENT_ENTITY", "DOB_MISMATCH": "DIFFERENT_ENTITY", "LOCATION_MISMATCH": "DIFFERENT_ENTITY",
    "NAME_MISMATCH_VERIFIED": "DIFFERENT_ENTITY", "ENTITY_TYPE_MISMATCH": "DIFFERENT_ENTITY", "DECEASED": "DIFFERENT_ENTITY",
    "NAME_DOB_LOCATION_MATCH": "SAME_ENTITY", "NAME_DOB_MATCH": "SAME_ENTITY", "NAME_LOCATION_MATCH": "SAME_ENTITY",
    "INSUFFICIENT_DATA": "REVIEW", "AMBIGUOUS_CUSTOMER_RECORD": "REVIEW",
}
DECISIONS = ["DIFFERENT_ENTITY", "SAME_ENTITY", "REVIEW"]
COST = {
    "DIFFERENT_ENTITY": {"DIFFERENT_ENTITY": 0, "SAME_ENTITY": 3, "REVIEW": 3},
    "SAME_ENTITY": {"DIFFERENT_ENTITY": 60, "SAME_ENTITY": 0, "REVIEW": 2},
    "REVIEW": {"DIFFERENT_ENTITY": 60, "SAME_ENTITY": 2, "REVIEW": 0},
}


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def ids_in(data):
    found = set()
    for name, key in (("customers", "record_id"), ("accounts", "account_id"), ("onboarding", "kyc_applicant_id"), ("kyc_checks", "check_id"), ("notes", "note_id"), ("search_results", "result_id"), ("hits", "hit_id"), ("alerts", "alert_id")):
        found |= {row[key] for row in read_jsonl(os.path.join(data, f"{name}.jsonl"))}
    return found


def validate(data, output):
    hits = {row["hit_id"]: row for row in read_jsonl(os.path.join(data, "hits.jsonl"))}
    records = {row["record_id"] for row in read_jsonl(os.path.join(data, "customers.jsonl"))}
    known = ids_in(data)
    errors, answers = [], {}
    with open(output, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            where = f"line {number}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append(f"{where}: not JSON ({error})")
                continue
            if not isinstance(row, dict):
                errors.append(f"{where}: not an object")
                continue
            hit_id = row.get("hit_id")
            if hit_id not in hits:
                errors.append(f"{where}: unknown hit_id {hit_id!r}")
                continue
            if hit_id in answers:
                errors.append(f"{where}: {hit_id} answered twice")
            if row.get("alert_id") != hits[hit_id]["alert_id"]:
                errors.append(f"{where}: alert_id should be {hits[hit_id]['alert_id']}")
            if row.get("decision") not in DECISIONS:
                errors.append(f"{where}: decision must be one of {DECISIONS}")
            if CODES.get(row.get("reason_code")) != row.get("decision"):
                errors.append(f"{where}: reason_code {row.get('reason_code')!r} does not belong to {row.get('decision')!r}")
            record = row.get("customer_record_id")
            if record not in (None, "", "AMBIGUOUS") and record not in records:
                errors.append(f"{where}: customer_record_id {record!r} is not in customers.jsonl")
            if not isinstance(row.get("reason"), str) or not row["reason"].strip():
                errors.append(f"{where}: reason is empty")
            evidence = row.get("evidence")
            if not isinstance(evidence, list):
                errors.append(f"{where}: evidence must be a list")
                evidence = []
            for item in evidence:
                if not isinstance(item, str):
                    errors.append(f"{where}: evidence item {item!r} is not a string")
                elif item.startswith("http://") or item.startswith("https://"):
                    continue
                elif re.match(r"^H-[0-9A-F]{6}#\w+$", item):
                    if item.split("#")[0] not in hits:
                        errors.append(f"{where}: evidence {item} names an unknown hit")
                elif item not in known:
                    errors.append(f"{where}: evidence {item} does not exist in the data folder")
            answers[hit_id] = row
    missing = [hit_id for hit_id in hits if hit_id not in answers]
    if missing:
        errors.append(f"{len(missing)} hits have no line (they count as REVIEW), e.g. {missing[:3]}")
    return answers, errors


def self_score(answers, practice):
    labels = read_jsonl(practice)
    cost = sum(COST[row["decision"]][answers.get(row["hit_id"], {}).get("decision", "REVIEW")] for row in labels)
    baseline = sum(COST[row["decision"]]["REVIEW"] for row in labels)
    right = [row for row in labels if answers.get(row["hit_id"], {}).get("decision") == row["decision"]]
    unsafe = sum(1 for row in labels if row["decision"] != "DIFFERENT_ENTITY" and answers.get(row["hit_id"], {}).get("decision") == "DIFFERENT_ENTITY")
    codes = sum(1 for row in right if answers[row["hit_id"]].get("reason_code") in row["reason_codes"])
    records = sum(1 for row in right if answers[row["hit_id"]].get("customer_record_id") in row["customer_record_ids"] or (row["customer_record_ids"] == ["AMBIGUOUS"] and answers[row["hit_id"]].get("customer_record_id") in (None, "", "AMBIGUOUS")))
    print(f"practice labels: {len(labels)} hits, {len(right)} right decisions, {unsafe} unsafe clearances")
    print(f"decision score {100 * max(0.0, 1 - cost / baseline):.1f} (0 = all REVIEW, 100 = perfect)")
    if right:
        print(f"on right decisions: reason code {codes / len(right):.0%}, customer record {records / len(right):.0%}")
    for row in labels:
        answer = answers.get(row["hit_id"], {})
        if answer.get("decision") != row["decision"]:
            print(f"  {row['hit_id']}: expected {row['decision']} {row['reason_codes']}, you said {answer.get('decision', 'nothing')} {answer.get('reason_code', '')}")


def main():
    parser = argparse.ArgumentParser(description="Check a screening output file the way the organisers do.")
    parser.add_argument("--data", required=True, help="the data folder the output was made from")
    parser.add_argument("--output", required=True, help="the output file, one JSON line per hit")
    parser.add_argument("--score", help="practice_labels.jsonl, to score the practice hits")
    args = parser.parse_args()
    answers, errors = validate(args.data, args.output)
    print(f"{len(answers)} lines read, {len(errors)} problems")
    for error in errors[:50]:
        print("  " + error)
    if args.score:
        self_score(answers, args.score)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
