"""Unit tests for Phase 3: Audit Engine & Remediation Planner."""

import json
from pathlib import Path
import sys
import unittest
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

# Avoid conflict with Python standard library 'code' module
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.config import (
    DeletionStatus,
    Phase,
    Operation,
    State,
)
from code.core.identity_resolver import UserIdentity
from code.core.intent_classifier import RequestIntent, RequestType
from code.core.evidence_manager import EvidenceItem
from code.core.planner import RemediationPlanner, step_sort_key
from code.core.auditor import DeletionAuditor, CaseAuditResult


class TestRemediationPlanner(unittest.TestCase):
    """Test step construction, phase ordering, operation ordering, tie-breaking, and serialization."""

    def setUp(self):
        self.planner = RemediationPlanner()

    def test_planner_not_applicable_produces_empty_list(self):
        """NOT_APPLICABLE status must produce an empty plan list and '[]'."""
        plan = self.planner.build_plan(
            status=DeletionStatus.NOT_APPLICABLE,
            findings=[{"system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT"}],
        )
        self.assertEqual(plan, [])
        self.assertEqual(self.planner.serialize_steps(plan), "[]")

    def test_planner_complete_verification_only_with_evidence(self):
        """COMPLETE status must contain only VERIFICATION steps with non-empty evidence_id."""
        verifications = [
            {"system_id": "account_service", "resource_id": "account_01", "operation": Operation.VERIFY_RECORD_ABSENT.value, "state": State.ABSENT.value, "evidence_id": "evidence_54"},
            {"system_id": "security_service", "resource_id": "audit_record_01", "operation": Operation.VERIFY_RECORD_PRESENT.value, "state": State.PRESENT.value, "evidence_id": "evidence_54"},
        ]
        plan = self.planner.build_plan(
            status=DeletionStatus.COMPLETE,
            verifications=verifications,
        )
        self.assertEqual(len(plan), 2)
        for s in plan:
            self.assertEqual(s["phase"], Phase.VERIFICATION.value)
            self.assertTrue(bool(s["evidence_id"]), "COMPLETE verification steps must have nonempty evidence_id")
        self.assertEqual(plan[0]["step_no"], 1)
        self.assertEqual(plan[1]["step_no"], 2)

    def test_planner_incomplete_phase_and_evidence_id_contract(self):
        """INCOMPLETE status must follow: FINDING (with evidence_id) -> REMEDIATION (evidence_id='') -> VERIFICATION (evidence_id='')."""
        findings = [
            {"system_id": "search_service", "resource_id": "search_01", "operation": Operation.REPORT_REMAINING_RECORD.value, "state": State.PRESENT.value, "evidence_id": "evidence_01"},
        ]
        remediations = [
            {"system_id": "search_service", "resource_id": "search_01", "operation": Operation.DELETE_RECORD.value, "state": State.ABSENT.value},
        ]
        verifications = [
            {"system_id": "search_service", "resource_id": "search_01", "operation": Operation.VERIFY_RECORD_ABSENT.value, "state": State.ABSENT.value},
        ]
        plan = self.planner.build_plan(
            status=DeletionStatus.INCOMPLETE,
            findings=findings,
            remediations=remediations,
            verifications=verifications,
        )
        self.assertEqual(len(plan), 3)
        # Phase 1: FINDING
        self.assertEqual(plan[0]["phase"], Phase.FINDING.value)
        self.assertEqual(plan[0]["evidence_id"], "evidence_01")
        # Phase 2: REMEDIATION
        self.assertEqual(plan[1]["phase"], Phase.REMEDIATION.value)
        self.assertEqual(plan[1]["evidence_id"], "")
        # Phase 3: VERIFICATION
        self.assertEqual(plan[2]["phase"], Phase.VERIFICATION.value)
        self.assertEqual(plan[2]["evidence_id"], "")

    def test_planner_operation_ordering_within_phases(self):
        """Operations within each phase must follow the problem statement table order."""
        # Unsorted remediations
        remediations = [
            {"system_id": "analytics_platform", "resource_id": "analytics_01", "operation": Operation.ANONYMIZE_RECORD.value, "state": State.ANONYMIZED.value},
            {"system_id": "integration_service", "resource_id": "data_flow_01", "operation": Operation.DISABLE_DATA_FLOW.value, "state": State.DISABLED.value},
            {"system_id": "backup_service", "resource_id": "backup_01", "operation": Operation.BLOCK_RESTORE.value, "state": State.BLOCKED.value},
            {"system_id": "account_service", "resource_id": "account_01", "operation": Operation.DELETE_RECORD.value, "state": State.ABSENT.value},
            {"system_id": "support_platform", "resource_id": "support_01", "operation": Operation.REDACT_RECORD.value, "state": State.REDACTED.value},
        ]
        plan = self.planner.build_plan(status=DeletionStatus.INCOMPLETE, remediations=remediations)
        ops = [s["operation"] for s in plan]
        expected_ops = [
            Operation.DISABLE_DATA_FLOW.value,
            Operation.BLOCK_RESTORE.value,
            Operation.DELETE_RECORD.value,
            Operation.REDACT_RECORD.value,
            Operation.ANONYMIZE_RECORD.value,
        ]
        self.assertEqual(ops, expected_ops)

    def test_planner_tie_breaking(self):
        """Equal phase and operation must be tie-broken by system_id ASC, then resource_id ASC."""
        verifications = [
            {"system_id": "support_platform", "resource_id": "support_99", "operation": Operation.VERIFY_RECORD_REDACTED.value, "state": State.REDACTED.value, "evidence_id": "e1"},
            {"system_id": "identity_service", "resource_id": "tombstone_05", "operation": Operation.VERIFY_RECORD_REDACTED.value, "state": State.REDACTED.value, "evidence_id": "e1"},
            {"system_id": "identity_service", "resource_id": "tombstone_02", "operation": Operation.VERIFY_RECORD_REDACTED.value, "state": State.REDACTED.value, "evidence_id": "e1"},
        ]
        plan = self.planner.build_plan(status=DeletionStatus.COMPLETE, verifications=verifications)
        res_keys = [(s["system_id"], s["resource_id"]) for s in plan]
        self.assertEqual(res_keys, [
            ("identity_service", "tombstone_02"),
            ("identity_service", "tombstone_05"),
            ("support_platform", "support_99"),
        ])


class MockIntentClassifier:
    """Mock intent classifier for controlled synthetic unit tests."""
    def __init__(self, is_del: bool = True):
        self.is_del = is_del

    def classify(self, text):
        return RequestIntent(
            is_deletion=self.is_del,
            request_type=RequestType.DELETION if self.is_del else RequestType.ACCESS,
            matched_patterns=["mock"],
            explanation="Mock intent",
        )


class MockIdentityResolver:
    """Mock identity resolver returning a fixed synthetic user identity."""
    def __init__(self, user: Optional[UserIdentity] = None):
        self.user = user or UserIdentity(
            user_id="user_synth_01",
            name="Synthetic User",
            current_email="synthetic.user@example.com",
            current_phone="+1 555-0199",
            current_email_hash="hash_synth_123",
            updated_at="2026-01-01T00:00:00Z",
            historical_emails=["old.synth@example.com"],
        )

    def resolve_by_email(self, email):
        return self.user

    def resolve_by_identifier(self, identifier):
        return self.user


class MockEvidenceManager:
    """Mock evidence manager returning controlled synthetic items."""
    def __init__(self, items: Optional[List[EvidenceItem]] = None):
        self._items = items or []

    def get_evidence_for_user(self, user, cutoff=None):
        eligible = []
        for it in self._items:
            if cutoff:
                if not cutoff.is_eligible(event_time=it.event_time, capture_time=it.captured_at):
                    continue
            eligible.append(it)
        return eligible


class TestDeletionAuditor(unittest.TestCase):
    """Test auditor policy decision rules, evidence corroboration, and risk detection."""

    def test_auditor_non_deletion_request(self):
        """Non-deletion request produces NOT_APPLICABLE and steps_json='[]'."""
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=False),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([]),
        )
        res = auditor.audit_case(
            case_id="case_test_nondel",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="NOT_STARTED",
            reported_at="2026-09-01T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="I am asking for an export of my data, not asking for deletion.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(res.steps, [])
        self.assertEqual(res.steps_json, "[]")

    def test_auditor_surviving_record_finding(self):
        """Surviving search index entry triggers REPORT_REMAINING_RECORD and DELETE_RECORD."""
        item = EvidenceItem(
            evidence_id="evidence_test_search",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="search_service",
            resource_id="search_101",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item]),
        )
        res = auditor.audit_case(
            case_id="case_test_search",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Please delete my account and records.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_REMAINING_RECORD.value, ops)
        self.assertIn(Operation.DELETE_RECORD.value, ops)
        self.assertIn(Operation.VERIFY_RECORD_ABSENT.value, ops)

    def test_auditor_active_sync_data_flow(self):
        """Active sync connector triggers REPORT_ACTIVE_DATA_FLOW and DISABLE_DATA_FLOW."""
        item = EvidenceItem(
            evidence_id="evidence_test_flow",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="integration_service",
            resource_id="data_flow_55",
            state="ACTIVE",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item]),
        )
        res = auditor.audit_case(
            case_id="case_test_flow",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my profile.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_ACTIVE_DATA_FLOW.value, ops)
        self.assertIn(Operation.DISABLE_DATA_FLOW.value, ops)
        self.assertIn(Operation.VERIFY_DATA_FLOW_DISABLED.value, ops)

    def test_auditor_restore_risk(self):
        """Unblocked backup triggers REPORT_RESTORE_RISK and BLOCK_RESTORE."""
        item = EvidenceItem(
            evidence_id="evidence_test_backup",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="backup_service",
            resource_id="backup_99",
            state="ACTIVE",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item]),
        )
        res = auditor.audit_case(
            case_id="case_test_backup",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my profile.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_RESTORE_RISK.value, ops)
        self.assertIn(Operation.BLOCK_RESTORE.value, ops)
        self.assertIn(Operation.VERIFY_RESTORE_BLOCKED.value, ops)

    def test_auditor_clean_vs_exposed_tombstone(self):
        """Clean tombstone produces VERIFY_RECORD_REDACTED; exposed tombstone produces REPORT_EXPOSED_PII."""
        # 1. Clean tombstone
        item_clean = EvidenceItem(
            evidence_id="evidence_tomb_clean",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="identity_service",
            resource_id="tombstone_clean_01",
            state="REDACTED",
            identifiers={"synthetic.user@example.com"},
        )
        auditor_clean = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item_clean]),
        )
        res_clean = auditor_clean.audit_case(
            case_id="case_tomb_clean",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my account.",
        )
        self.assertEqual(res_clean.deletion_status, DeletionStatus.COMPLETE)
        self.assertIn(Operation.VERIFY_RECORD_REDACTED.value, [s["operation"] for s in res_clean.steps])

        # 2. Exposed tombstone
        item_exposed = EvidenceItem(
            evidence_id="evidence_tomb_exp",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="identity_service",
            resource_id="tombstone_exp_02",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor_exp = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item_exposed]),
        )
        res_exp = auditor_exp.audit_case(
            case_id="case_tomb_exp",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my account.",
        )
        self.assertEqual(res_exp.deletion_status, DeletionStatus.INCOMPLETE)
        ops_exp = [s["operation"] for s in res_exp.steps]
        self.assertIn(Operation.REPORT_EXPOSED_PII.value, ops_exp)
        self.assertIn(Operation.REDACT_RECORD.value, ops_exp)

    def test_auditor_post_cutoff_exclusion(self):
        """Evidence captured after audit_at must be strictly excluded."""
        # Evidence created after audit_at
        late_item = EvidenceItem(
            evidence_id="evidence_late",
            source_type="TEST",
            captured_at="2026-09-20T00:00:00Z",  # After cutoff 2026-09-15
            event_time="2026-09-20T00:00:00Z",
            system_id="search_service",
            resource_id="search_late_01",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([late_item]),
        )
        res = auditor.audit_case(
            case_id="case_test_cutoff",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my profile.",
        )
        # Late item was excluded, so no finding was triggered for search_late_01
        self.assertNotIn("search_late_01", [s["resource_id"] for s in res.steps])

    def test_auditor_shared_support_message_redact(self):
        """Shared support messages must trigger REPORT_EXPOSED_PII -> REDACT_RECORD -> VERIFY_RECORD_REDACTED."""
        support_item = EvidenceItem(
            evidence_id="evidence_sup_01",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="support_platform",
            resource_id="support_ticket_55",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([support_item]),
        )
        res = auditor.audit_case(
            case_id="case_sup_redact",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Please delete all my records.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_EXPOSED_PII.value, ops)
        self.assertIn(Operation.REDACT_RECORD.value, ops)
        self.assertIn(Operation.VERIFY_RECORD_REDACTED.value, ops)

    def test_auditor_analytics_anonymize(self):
        """Attributable analytics profiles must trigger REPORT_EXPOSED_PII -> ANONYMIZE_RECORD -> VERIFY_RECORD_ANONYMIZED."""
        analytics_item = EvidenceItem(
            evidence_id="evidence_an_01",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="analytics_platform",
            resource_id="analytics_prof_88",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([analytics_item]),
        )
        res = auditor.audit_case(
            case_id="case_an_anon",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my account permanently.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_EXPOSED_PII.value, ops)
        self.assertIn(Operation.ANONYMIZE_RECORD.value, ops)
        self.assertIn(Operation.VERIFY_RECORD_ANONYMIZED.value, ops)

    def test_auditor_security_audit_retain(self):
        """Security audit logs must be RETAINED and verified with VERIFY_RECORD_PRESENT with evidence."""
        audit_item = EvidenceItem(
            evidence_id="evidence_sec_01",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="security_service",
            resource_id="audit_record_900",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([audit_item]),
        )
        res = auditor.audit_case(
            case_id="case_sec_retain",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my data.",
        )
        # RETAIN does not trigger a finding or incomplete status if no other issues exist
        self.assertEqual(res.deletion_status, DeletionStatus.COMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.VERIFY_RECORD_PRESENT.value, ops)
        sec_step = next(s for s in res.steps if s["resource_id"] == "audit_record_900")
        self.assertEqual(sec_step["evidence_id"], "evidence_sec_01")
        self.assertEqual(sec_step["state"], State.PRESENT.value)

    def test_auditor_conflicting_evidence_resolution(self):
        """When conflicting evidence exists, the latest verified state at or before audit_at determines the state."""
        # Item 1: earlier deleted / absent
        item_earlier = EvidenceItem(
            evidence_id="evidence_search_early",
            source_type="TEST",
            captured_at="2026-09-05T00:00:00Z",
            event_time="2026-09-05T00:00:00Z",
            system_id="search_service",
            resource_id="search_sync_01",
            state="ABSENT",
            identifiers={"synthetic.user@example.com"},
        )
        # Item 2: later recreated / present via replica sync
        item_later = EvidenceItem(
            evidence_id="evidence_search_later",
            source_type="TEST",
            captured_at="2026-09-10T00:00:00Z",
            event_time="2026-09-10T00:00:00Z",
            system_id="search_service",
            resource_id="search_sync_01",
            state="PRESENT",
            identifiers={"synthetic.user@example.com"},
        )
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([item_earlier, item_later]),
        )
        res = auditor.audit_case(
            case_id="case_conflict",
            email="synthetic.user@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T10:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my data.",
        )
        # Since it is PRESENT at audit_at, it must be flagged as INCOMPLETE
        self.assertEqual(res.deletion_status, DeletionStatus.INCOMPLETE)
        ops = [s["operation"] for s in res.steps]
        self.assertIn(Operation.REPORT_REMAINING_RECORD.value, ops)

    def test_batch_request_disambiguation(self):
        """Batch of requests with the same reported_at are disambiguated deterministically."""
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([]),
        )
        reqs = [
            {"case_id": "case_101", "email": "synthetic.user@example.com", "reported_status": "COMPLETE", "reported_at": "2026-09-02T12:00:00Z"},
            {"case_id": "case_102", "email": "synthetic.user@example.com", "reported_status": "COMPLETE", "reported_at": "2026-09-02T12:00:00Z"},
        ]
        auditor.index_requests(reqs)
        self.assertIn("2026-09-02T12:00:00Z", auditor._requests_by_reported_at)
        self.assertEqual(len(auditor._requests_by_reported_at["2026-09-02T12:00:00Z"]), 2)

    def test_non_complete_account_status_matching(self):
        """Non-complete cases match FAILED or PARTIAL account actions rather than SUCCESS."""
        auditor = DeletionAuditor(
            classifier=MockIntentClassifier(is_del=True),
            resolver=MockIdentityResolver(),
            manager=MockEvidenceManager([]),
        )
        res = auditor.audit_case(
            case_id="case_test_partial",
            email="synthetic.user@example.com",
            requested_at="2026-08-27T12:00:00Z",
            reported_status="PARTIALLY_COMPLETE",
            reported_at="2026-08-30T12:00:00Z",
            audit_at="2026-09-15T12:00:00Z",
            request_text="Delete my account.",
        )
        self.assertEqual(res.deletion_status, DeletionStatus.COMPLETE)


if __name__ == "__main__":
    unittest.main()

