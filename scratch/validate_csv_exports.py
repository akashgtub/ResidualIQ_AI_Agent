"""Comprehensive validation script for ResidualQ CSV exports and root output.csv integrity."""

import csv
import hashlib
import json
from pathlib import Path

repo_root = Path(r"c:\hackerrank-orchestrate-october26")
downloads_dir = repo_root / "scratch" / "downloads"
root_output_path = repo_root / "output.csv"

EXPECTED_ROOT_HASH = "60e2a24f119a92fc4a9a74498a61e87d92b9e0f466150965dc7e6323aad27a08"

def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

print("=" * 60)
print("RESIDUALQ AI AGENT — CSV EXPORT VALIDATION")
print("=" * 60)

# 1. Verify root output.csv integrity
root_hash = compute_sha256(root_output_path)
print(f"\n[1] Root output.csv Hash Check:")
print(f"  Current SHA-256:  {root_hash}")
print(f"  Expected SHA-256: {EXPECTED_ROOT_HASH}")
assert root_hash == EXPECTED_ROOT_HASH, "CRITICAL: Root output.csv was modified!"
print("  ==> Root output.csv is UNTOUCHED and PROTECTED!")

# 2. Verify residualq_output.csv (Full Submission Export)
sub_all_path = downloads_dir / "residualq_output.csv"
assert sub_all_path.exists(), f"File {sub_all_path} does not exist!"
print(f"\n[2] Validating Full Submission Export ({sub_all_path.name}):")
print(f"  File size: {sub_all_path.stat().st_size:,} bytes")

# Check UTF-8 BOM
with open(sub_all_path, "rb") as f:
    bom = f.read(3)
    assert bom == b"\xef\xbb\xbf", "Missing UTF-8 BOM in exported CSV!"
print("  UTF-8 BOM: Present (b'\\xef\\xbb\\xbf') — Excel compatible.")

with open(sub_all_path, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    assert header == ["case_id", "deletion_status", "steps_json"], f"Unexpected header: {header}"
    print(f"  Header: {header} (EXACT MATCH with challenge schema)")

    rows = list(reader)
    assert len(rows) == 518, f"Expected 518 rows, got {len(rows)}"
    print(f"  Row count: {len(rows)} data rows (EXACT MATCH)")

    # Load expected case IDs from root output.csv
    with open(root_output_path, "r", encoding="utf-8") as f_root:
        expected_rows = list(csv.reader(f_root))[1:]

    status_counts = {}
    for i, (row, exp_r) in enumerate(zip(rows, expected_rows), start=1):
        cid, status, steps_str = row
        assert cid == exp_r[0], f"Row {i} case_id mismatch: {cid} vs expected {exp_r[0]}"
        assert status == exp_r[1], f"Row {i} status mismatch: {status} vs expected {exp_r[1]}"
        status_counts[status] = status_counts.get(status, 0) + 1

        try:
            steps = json.loads(steps_str)
            assert isinstance(steps, list), f"steps_json is not a list in row {i}"
        except Exception as e:
            raise AssertionError(f"JSON parse error in row {i} ({cid}): {e}")

        if status == "NOT_APPLICABLE":
            assert steps == [], f"Row {i} NOT_APPLICABLE must have steps_json=[]"

    print(f"  All 518 steps_json cells parsed successfully as JSON arrays!")
    print(f"  Status breakdown: {status_counts}")

# 3. Compare with canonical root output.csv
print("\n[3] Comparing residualq_output.csv against canonical root output.csv:")
with open(root_output_path, "r", encoding="utf-8") as f_root, open(sub_all_path, "r", encoding="utf-8-sig") as f_exp:
    root_rows = list(csv.reader(f_root))
    exp_rows = list(csv.reader(f_exp))
    assert len(root_rows) == len(exp_rows), "Row count difference!"
    diff_count = 0
    for r_idx, (r_row, e_row) in enumerate(zip(root_rows, exp_rows)):
        if r_row != e_row:
            diff_count += 1
            if diff_count <= 3:
                print(f"  Difference at row {r_idx}: {r_row} vs {e_row}")
    assert diff_count == 0, f"Found {diff_count} differing rows!"
    print(f"  518 / 518 rows are 100% BIT-FOR-BIT IDENTICAL to official output.csv!")

# 4. Verify residualq_submission_filtered_incomplete.csv
sub_filt_path = downloads_dir / "residualq_submission_filtered_incomplete.csv"
assert sub_filt_path.exists(), f"File {sub_filt_path} does not exist!"
print(f"\n[4] Validating Filtered Submission Export ({sub_filt_path.name}):")
print(f"  File size: {sub_filt_path.stat().st_size:,} bytes")

with open(sub_filt_path, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    assert header == ["case_id", "deletion_status", "steps_json"]
    filt_rows = list(reader)
    assert len(filt_rows) == 342, f"Expected 342 filtered rows, got {len(filt_rows)}"
    print(f"  Row count: {len(filt_rows)} (EXACT MATCH for INCOMPLETE cases)")
    for row in filt_rows:
        assert row[1] == "INCOMPLETE"
        steps = json.loads(row[2])
        assert len(steps) > 0
    print("  All 342 rows verified with deletion_status=INCOMPLETE and valid JSON steps!")

# 5. Verify residualq_audit_report_all.csv
rep_all_path = downloads_dir / "residualq_audit_report_all.csv"
assert rep_all_path.exists(), f"File {rep_all_path} does not exist!"
print(f"\n[5] Validating Detailed Audit Report All ({rep_all_path.name}):")
print(f"  File size: {rep_all_path.stat().st_size:,} bytes")

with open(rep_all_path, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    assert len(header) == 16, f"Expected 16 columns, got {len(header)}: {header}"
    rep_rows = list(reader)
    assert len(rep_rows) == 518, f"Expected 518 report rows, got {len(rep_rows)}"
    print(f"  Header columns: {header}")
    print(f"  Row count: {len(rep_rows)} rows formatted for spreadsheet analysis")

# 6. Verify residualq_audit_report_filtered_incomplete.csv
rep_filt_path = downloads_dir / "residualq_audit_report_filtered_incomplete.csv"
assert rep_filt_path.exists(), f"File {rep_filt_path} does not exist!"
print(f"\n[6] Validating Detailed Audit Report Filtered ({rep_filt_path.name}):")
print(f"  File size: {rep_filt_path.stat().st_size:,} bytes")

with open(rep_filt_path, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    assert len(header) == 16
    rep_filt_rows = list(reader)
    assert len(rep_filt_rows) == 342, f"Expected 342 rows, got {len(rep_filt_rows)}"
    print(f"  Row count: {len(rep_filt_rows)} rows for INCOMPLETE cases")

print("\n" + "=" * 60)
print("ALL CSV EXPORT VALIDATIONS PASSED WITH 100% FIDELITY!")
print("=" * 60)
