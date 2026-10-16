"""Run expert-labeled JSONL cases repeatedly through the same API as the UI.

Usage: python -m evals.run cases.jsonl --repeats 10 --url http://127.0.0.1:8000
No patient identifiers should be included in the input or output files.
"""

import argparse
import csv
import json
from pathlib import Path

import httpx


def run(source: Path, repeats: int, url: str, destination: Path):
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    for case in rows:
        if not case.get("case_id") or not case.get("expected_outcome_id") or not case.get("reviewed_by"):
            raise ValueError("Each case needs case_id, expected_outcome_id and reviewed_by")
    with httpx.Client(timeout=110) as client, destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "repeat", "expected_outcome_id", "actual_outcome_id", "status", "match", "error"])
        writer.writeheader()
        for case in rows:
            payload = case["input"]
            for repeat in range(1, repeats + 1):
                row = {"case_id": case["case_id"], "repeat": repeat,
                       "expected_outcome_id": case["expected_outcome_id"],
                       "actual_outcome_id": "", "status": "", "match": False, "error": ""}
                try:
                    response = client.post(url.rstrip("/") + "/api/assess", json=payload)
                    response.raise_for_status()
                    result = response.json()
                    row.update(actual_outcome_id=result["outcome_id"], status=result["status"],
                               match=result["outcome_id"] == case["expected_outcome_id"])
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    row["error"] = str(exc)
                writer.writerow(row)
                stream.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("eval-results.csv"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    run(args.cases, args.repeats, args.url, args.output)

