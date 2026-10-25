import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

# Avoid conflict with Python standard library 'code' module
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.config import DeletionStatus, Phase, Operation, State
from code.evaluation.main import (
    ClassMetrics,
    FieldMetrics,
    DeletionEvaluator,
    safe_div,
)


class TestEvaluatorMetrics(unittest.TestCase):
    """Test metric computations and edge-case denominator handling."""

    def test_safe_div_zero_denominator(self):
        """safe_div must return 0.0 when denominator is 0 without raising ZeroDivisionError."""
        self.assertEqual(safe_div(0, 0), 0.0)
        self.assertEqual(safe_div(10, 0), 0.0)
        self.assertEqual(safe_div(5, 10), 0.5)

    def test_class_metrics_calculations(self):
        """Test Precision, Recall, and F1 calculations on ClassMetrics."""
        cm_perfect = ClassMetrics(tp=10, fp=0, fn=0, tn=20)
        self.assertEqual(cm_perfect.precision, 1.0)
        self.assertEqual(cm_perfect.recall, 1.0)
        self.assertEqual(cm_perfect.f1, 1.0)

        cm = ClassMetrics(tp=8, fp=2, fn=4, tn=16)
        self.assertAlmostEqual(cm.precision, 0.8)
        self.assertAlmostEqual(cm.recall, 8 / 12)
        self.assertAlmostEqual(cm.f1, 2 * 0.8 * (8 / 12) / (0.8 + 8 / 12))

        # Zero denominator case (no positive predictions)
        cm_zero = ClassMetrics(tp=0, fp=0, fn=5, tn=25)
        self.assertEqual(cm_zero.precision, 0.0)
        self.assertEqual(cm_zero.recall, 0.0)
        self.assertEqual(cm_zero.f1, 0.0)

    def test_field_metrics_calculations(self):
        """Test FieldMetrics calculations."""
        fm = FieldMetrics(field_name="operation", tp=18, fp=2, fn=2)
        self.assertAlmostEqual(fm.precision, 0.9)
        self.assertAlmostEqual(fm.recall, 0.9)
        self.assertAlmostEqual(fm.f1, 0.9)

        # Empty field metrics (denominator zero)
        fm_empty = FieldMetrics(field_name="phase", tp=0, fp=0, fn=0)
        self.assertEqual(fm_empty.precision, 0.0)
        self.assertEqual(fm_empty.recall, 0.0)
        self.assertEqual(fm_empty.f1, 0.0)

    def test_duplicate_steps_in_prediction(self):
        """Duplicate predicted steps must be treated as false positives (extraneous)."""
        # Ground truth has 1 step
        truth_steps = [
            {
                "step_no": 1,
                "phase": "FINDING",
                "system_id": "account_service",
                "resource_id": "account_001",
                "operation": "REPORT_REMAINING_RECORD",
                "state": "PRESENT",
                "evidence_id": "evidence_01",
            }
        ]
        # Prediction has duplicated step
        pred_steps = [
            {
                "step_no": 1,
                "phase": "FINDING",
                "system_id": "account_service",
                "resource_id": "account_001",
                "operation": "REPORT_REMAINING_RECORD",
                "state": "PRESENT",
                "evidence_id": "evidence_01",
            },
            {
                "step_no": 2,
                "phase": "FINDING",
                "system_id": "account_service",
                "resource_id": "account_001",
                "operation": "REPORT_REMAINING_RECORD",
                "state": "PRESENT",
                "evidence_id": "evidence_01",
            },
        ]

        fm = FieldMetrics(field_name="operation")
        # Multiset matching logic
        t_counts: Dict[str, int] = {}
        for s in truth_steps:
            t_counts[s["operation"]] = t_counts.get(s["operation"], 0) + 1

        matched = 0
        for s in pred_steps:
            op = s["operation"]
            if t_counts.get(op, 0) > 0:
                matched += 1
                t_counts[op] -= 1

        fm.tp += matched
        fm.fp += (len(pred_steps) - matched)
        fm.fn += (len(truth_steps) - matched)

        # Matched 1, extra 1 (duplicate), missing 0
        self.assertEqual(fm.tp, 1)
        self.assertEqual(fm.fp, 1)
        self.assertEqual(fm.fn, 0)
        self.assertEqual(fm.precision, 0.5)
        self.assertEqual(fm.recall, 1.0)

    def test_extra_and_missing_steps(self):
        """Extra predicted steps must count as FP, and missing truth steps must count as FN."""
        truth_steps = [
            {"operation": "REPORT_REMAINING_RECORD"},
            {"operation": "DELETE_RECORD"},
            {"operation": "VERIFY_RECORD_ABSENT"},
        ]
        pred_steps = [
            {"operation": "REPORT_REMAINING_RECORD"},
            {"operation": "DISABLE_DATA_FLOW"},  # extra
        ]

        fm = FieldMetrics(field_name="operation")
        t_counts = {}
        for s in truth_steps:
            t_counts[s["operation"]] = t_counts.get(s["operation"], 0) + 1

        matched = 0
        for s in pred_steps:
            op = s["operation"]
            if t_counts.get(op, 0) > 0:
                matched += 1
                t_counts[op] -= 1

        fm.tp += matched
        fm.fp += (len(pred_steps) - matched)
        fm.fn += (len(truth_steps) - matched)

        self.assertEqual(fm.tp, 1)
        self.assertEqual(fm.fp, 1)  # DISABLE_DATA_FLOW is extra
        self.assertEqual(fm.fn, 2)  # DELETE_RECORD and VERIFY_RECORD_ABSENT missing
        self.assertEqual(fm.precision, 0.5)
        self.assertAlmostEqual(fm.recall, 1 / 3)

    def test_evidence_id_contract_validation(self):
        """Test validation rules for evidence IDs across COMPLETE and INCOMPLETE cases."""
        valid_complete_steps = [
            {"step_no": 1, "phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "evidence_id": "evidence_92"},
            {"step_no": 2, "phase": "VERIFICATION", "operation": "VERIFY_RESTORE_BLOCKED", "evidence_id": "evidence_92"},
        ]
        invalid_complete_empty_evidence = [
            {"step_no": 1, "phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "evidence_id": ""},
        ]
        valid_incomplete_steps = [
            {"step_no": 1, "phase": "FINDING", "operation": "REPORT_REMAINING_RECORD", "evidence_id": "evidence_59"},
            {"step_no": 2, "phase": "REMEDIATION", "operation": "DELETE_RECORD", "evidence_id": ""},
            {"step_no": 3, "phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "evidence_id": ""},
        ]
        invalid_incomplete_nonempty_remediation_evidence = [
            {"step_no": 1, "phase": "FINDING", "operation": "REPORT_REMAINING_RECORD", "evidence_id": "evidence_59"},
            {"step_no": 2, "phase": "REMEDIATION", "operation": "DELETE_RECORD", "evidence_id": "evidence_01"},  # Invalid: future remediation cannot cite past evidence
            {"step_no": 3, "phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "evidence_id": ""},
        ]

        def check_evidence_contract(status: str, steps: List[Dict[str, Any]]) -> bool:
            if status == "COMPLETE":
                return all(s.get("evidence_id") != "" for s in steps)
            elif status == "INCOMPLETE":
                findings_ok = all(s.get("evidence_id") != "" for s in steps if s.get("phase") == "FINDING")
                future_ok = all(s.get("evidence_id") == "" for s in steps if s.get("phase") in ("REMEDIATION", "VERIFICATION"))
                return findings_ok and future_ok
            elif status == "NOT_APPLICABLE":
                return len(steps) == 0
            return False

        self.assertTrue(check_evidence_contract("COMPLETE", valid_complete_steps))
        self.assertFalse(check_evidence_contract("COMPLETE", invalid_complete_empty_evidence))
        self.assertTrue(check_evidence_contract("INCOMPLETE", valid_incomplete_steps))
        self.assertFalse(check_evidence_contract("INCOMPLETE", invalid_incomplete_nonempty_remediation_evidence))
        self.assertTrue(check_evidence_contract("NOT_APPLICABLE", []))
        self.assertFalse(check_evidence_contract("NOT_APPLICABLE", valid_complete_steps))

    def test_synthetic_cases_pass(self):
        """Test that all three synthetic evaluation cases execute and pass."""
        evaluator = DeletionEvaluator()
        synth_results = evaluator.run_synthetic_cases()
        self.assertEqual(len(synth_results), 3)
        for sc in synth_results:
            self.assertTrue(sc["passed"], f"Synthetic case failed: {sc['case_id']}")


if __name__ == "__main__":
    unittest.main()
