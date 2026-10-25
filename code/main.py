"""Production entry point for Ghost Data Still Exists deletion audit agent.

Processes dataset/deletion_requests.csv (518 evaluation requests), audits each request
against participant-visible evidence up to that case's audit_at cutoff, applies
deletion_rules.csv, formulates ordered remediation plans, and writes root output.csv.
"""

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Avoid conflict with Python standard library 'code' module
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.config import (
    DELETION_REQUESTS_PATH,
    OUTPUT_PATH,
    DeletionStatus,
)
from code.core.auditor import DeletionAuditor, CaseAuditResult


def parse_case_num(case_id: str) -> int:
    """Extract integer case number for deterministic sorting."""
    parts = case_id.split("_")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def run_pipeline(
    input_path: Path = DELETION_REQUESTS_PATH,
    output_path: Path = OUTPUT_PATH,
) -> List[Dict[str, Any]]:
    """Execute full audit pipeline across all cases in input_path and write output_path."""
    print("=" * 70)
    print("Ghost Data Still Exists — Production Audit Pipeline")
    print("=" * 70)
    print(f"Input requests:  {input_path}")
    print(f"Output template: {output_path}")

    if not input_path.exists():
        raise FileNotFoundError(f"Input requests file not found: {input_path}")

    # Initialize auditor and pre-load all participant evidence
    t0 = time.time()
    print("\nInitializing DeletionAuditor and ingesting participant evidence...")
    auditor = DeletionAuditor()
    print("Evidence ingested and indexed.")

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        requests = list(reader)

    auditor.index_requests(requests)

    total_requests = len(requests)
    print(f"Total requests to process: {total_requests}")

    output_rows = []
    status_counts = {
        DeletionStatus.COMPLETE.value: 0,
        DeletionStatus.INCOMPLETE.value: 0,
        DeletionStatus.NOT_APPLICABLE.value: 0,
    }

    t_start = time.time()
    for idx, row in enumerate(requests, 1):
        cid = row["case_id"]
        res: CaseAuditResult = auditor.audit_case(
            case_id=cid,
            email=row["email"],
            requested_at=row["requested_at"],
            reported_status=row["reported_status"],
            reported_at=row["reported_at"],
            audit_at=row["audit_at"],
            request_text=row["request_text"],
        )

        status_val = res.deletion_status.value
        status_counts[status_val] = status_counts.get(status_val, 0) + 1

        output_rows.append({
            "case_id": res.case_id,
            "deletion_status": status_val,
            "steps_json": res.steps_json,
        })

        if idx % 50 == 0 or idx == total_requests:
            elapsed = time.time() - t_start
            print(f"Processed {idx:3d}/{total_requests} cases ({idx/total_requests*100:5.1f}%) in {elapsed:.1f}s")

    # Sort output rows by case_id ascending (numerically)
    output_rows.sort(key=lambda r: parse_case_num(r["case_id"]))

    # Write root output.csv
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["case_id", "deletion_status", "steps_json"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    total_time = time.time() - t0
    print("\n" + "=" * 70)
    print("Pipeline Execution Complete!")
    print(f"Total rows written: {len(output_rows)}")
    print(f"Output path:        {output_path.resolve()}")
    print(f"Total runtime:      {total_time:.2f}s (avg {total_time/total_requests*1000:.1f}ms/request)")
    print("\nStatus Distribution:")
    for status, count in status_counts.items():
        pct = count / total_requests * 100
        print(f"  - {status:<15}: {count:3d} ({pct:5.1f}%)")
    print("=" * 70)

    return output_rows


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists Audit Agent")
    parser.add_argument(
        "--input",
        type=Path,
        default=DELETION_REQUESTS_PATH,
        help="Path to deletion requests CSV (default: dataset/deletion_requests.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Path to output CSV (default: output.csv)",
    )
    args = parser.parse_args()
    run_pipeline(input_path=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
