"""Unit tests for Phase 2: Evidence Parsers & Temporal Indexing."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import sqlite3
import json

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

# Avoid conflict with Python standard library 'code' module
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

from code.config import (
    REPO_ROOT,
    DATASET_DIR,
    EVIDENCE_FILES_PATH,
    SYSTEM_ACTIVITY_PATH,
)
from code.core.temporal_filter import (
    TemporalFilter,
    parse_iso_timestamp,
    is_at_or_before,
)
from code.core.evidence_manager import (
    EvidenceManager,
    EvidenceItem,
)
from code.core.identity_resolver import UserIdentity


class TestTemporalFilter(unittest.TestCase):
    """Test ISO timestamp parsing, timezone handling, and cutoff filtering."""

    def test_parse_valid_iso_utc(self):
        dt = parse_iso_timestamp("2026-09-15T11:59:39Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 9)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 11)
        self.assertEqual(dt.minute, 59)
        self.assertEqual(dt.second, 39)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_timezone_offsets(self):
        # +02:00 offset should convert to UTC (14:00+02:00 -> 12:00 UTC)
        dt = parse_iso_timestamp("2026-09-15T14:00:00+02:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 12)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_malformed_and_missing_timestamps(self):
        self.assertIsNone(parse_iso_timestamp(None))
        self.assertIsNone(parse_iso_timestamp(""))
        self.assertIsNone(parse_iso_timestamp("   "))
        self.assertIsNone(parse_iso_timestamp("invalid_date_format"))
        self.assertIsNone(parse_iso_timestamp("2026-99-99T99:99:99Z"))

    def test_is_at_or_before(self):
        cutoff = "2026-09-15T12:00:00Z"
        self.assertTrue(is_at_or_before("2026-09-15T11:59:59Z", cutoff))
        self.assertTrue(is_at_or_before("2026-09-15T12:00:00Z", cutoff))
        self.assertFalse(is_at_or_before("2026-09-15T12:00:01Z", cutoff))
        self.assertFalse(is_at_or_before("2026-09-16T00:00:00Z", cutoff))

    def test_conservative_missing_timestamp_rejection(self):
        cutoff = "2026-09-15T12:00:00Z"
        # By default, unknown/malformed timestamps cannot be assumed to be pre-cutoff
        self.assertFalse(is_at_or_before(None, cutoff))
        self.assertFalse(is_at_or_before("malformed", cutoff))
        # With allow_missing=True, returns True
        self.assertTrue(is_at_or_before(None, cutoff, allow_missing=True))

    def test_temporal_filter_class(self):
        tf = TemporalFilter("2026-09-15T12:00:00Z")
        # Eligible pre-cutoff event
        self.assertTrue(tf.is_eligible(event_time="2026-09-15T11:00:00Z"))
        # Ineligible post-cutoff event
        self.assertFalse(tf.is_eligible(event_time="2026-09-15T13:00:00Z"))
        # Event time post-cutoff even if captured earlier is ineligible
        self.assertFalse(tf.is_eligible(event_time="2026-09-15T13:00:00Z", capture_time="2026-09-15T10:00:00Z"))
        # Neither event nor capture time provided
        self.assertFalse(tf.is_eligible(event_time=None, capture_time=None))


class TestEvidenceManager(unittest.TestCase):
    """Test multimodal evidence parsers, temporal querying, and identity indexing."""

    @classmethod
    def setUpClass(cls):
        cls.manager = EvidenceManager()
        cls.manager.load_manifest()

    def test_manifest_loaded(self):
        self.assertGreater(len(self.manager._manifest), 90, "Should load all evidence manifest records")
        first_id = list(self.manager._manifest.keys())[0]
        meta = self.manager._manifest[first_id]
        self.assertIn("file_path", meta)
        self.assertIn("origin", meta)
        self.assertIn("captured_at", meta)

    def test_sql_snapshot_parsing(self):
        # Create an isolated temporary SQLite-compatible SQL snapshot
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
            f.write("""
            BEGIN TRANSACTION;
            CREATE TABLE customer_profiles (
                resource_id TEXT PRIMARY KEY,
                customer_reference TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                account_status TEXT NOT NULL
            );
            INSERT INTO customer_profiles VALUES ('account_test_01', 'user_test_99', 'Test User', 'test.user@example.com', '+1 555-0199', 'ACTIVE');
            COMMIT;
            """)
            temp_sql_path = Path(f.name)

        try:
            items = self.manager.parse_sql_file(
                file_id="evidence_sql_test",
                sql_path=temp_sql_path,
                origin="account_service",
                captured_at="2026-09-01T10:00:00Z",
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.evidence_id, "evidence_sql_test")
            self.assertEqual(item.resource_id, "account_test_01")
            self.assertEqual(item.system_id, "account_service")
            self.assertIn("user_test_99", item.identifiers)
            self.assertIn("test.user@example.com", item.identifiers)
            self.assertEqual(item.state, "PRESENT")
        finally:
            temp_sql_path.unlink()

    def test_json_record_parsing(self):
        bundle_data = {
            "exported_at": "2026-09-10T12:00:00Z",
            "snapshots": [
                {
                    "captured_at": "2026-09-10T11:00:00Z",
                    "data_store": "search_service",
                    "collection": "customer_search_documents",
                    "records": [
                        {
                            "resource_id": "search_test_01",
                            "customer_reference": "user_test_88",
                            "email": "search.target@example.com",
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bundle_data, f)
            temp_json_path = Path(f.name)

        try:
            items = self.manager.parse_json_record_file(
                file_id="evidence_json_test",
                json_path=temp_json_path,
                origin="records_assurance",
                captured_at="2026-09-10T12:00:00Z",
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.evidence_id, "evidence_json_test")
            self.assertEqual(item.resource_id, "search_test_01")
            self.assertEqual(item.system_id, "search_service")
            self.assertIn("user_test_88", item.identifiers)
            self.assertIn("search.target@example.com", item.identifiers)
        finally:
            temp_json_path.unlink()

    def test_txt_record_parsing(self):
        txt_content = """CUSTOMER PLATFORM - SHIFT HANDOVER
- 2026-09-15T12:00:00Z | account_service | account_999 | USER_PROFILE | NOT_FOUND | deleted.user@example.com
- 2026-09-15T12:00:00Z | search_service | search_888 | SEARCH_INDEX_ENTRY | FOUND | active.search@example.com
"""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(txt_content)
            temp_txt_path = Path(f.name)

        try:
            items = self.manager.parse_txt_record_file(
                file_id="evidence_txt_test",
                txt_path=temp_txt_path,
                origin="shift_handover",
                captured_at="2026-09-15T12:00:00Z",
            )
            self.assertEqual(len(items), 2)
            # First item NOT_FOUND -> state ABSENT
            self.assertEqual(items[0].resource_id, "account_999")
            self.assertEqual(items[0].state, "ABSENT")
            self.assertIn("deleted.user@example.com", items[0].identifiers)
            # Second item FOUND -> state PRESENT
            self.assertEqual(items[1].resource_id, "search_888")
            self.assertEqual(items[1].state, "PRESENT")
            self.assertIn("active.search@example.com", items[1].identifiers)
        finally:
            temp_txt_path.unlink()

    def test_log_file_parsing(self):
        log_content = """2026-07-28T05:51:21Z [INFO] [account_service] [tr-6074163] profile_lookup_completed: instance="account-5" resource_id="account_log_01" correlation_key="log.user@example.com" rows="0" http_status="404"
2026-07-28T05:51:41Z [WARN] [support_platform] [tr-2053433] message_pii_scan: instance="support-6" resource_id="support_log_02" matched_value="support.user@example.com" detector="direct_identifier" rows="1"
"""
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write(log_content)
            temp_log_path = Path(f.name)

        try:
            items = self.manager.parse_log_file(
                file_id="evidence_log_test",
                log_path=temp_log_path,
                origin="observability",
                captured_at="2026-07-28T06:00:00Z",
            )
            self.assertEqual(len(items), 2)
            # Item 1: 404/rows=0 -> ABSENT
            self.assertEqual(items[0].resource_id, "account_log_01")
            self.assertEqual(items[0].state, "ABSENT")
            self.assertIn("log.user@example.com", items[0].identifiers)
            # Item 2: rows=1 -> PRESENT
            self.assertEqual(items[1].resource_id, "support_log_02")
            self.assertEqual(items[1].state, "PRESENT")
            self.assertIn("support.user@example.com", items[1].identifiers)
        finally:
            temp_log_path.unlink()

    def test_image_fallback_when_ocr_unavailable(self):
        from PIL import Image
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as f:
            img = Image.new("RGB", (200, 100), color="white")
            img.save(f, format="PNG")
            temp_img_path = Path(f.name)

        try:
            # Without OCR runner, should gracefully return item with ocr_available=False
            items = self.manager.parse_image_file(
                file_id="evidence_img_test",
                image_path=temp_img_path,
                origin="admin_console",
                captured_at="2026-08-01T10:00:00Z",
                ocr_runner=None,
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.evidence_id, "evidence_img_test")
            self.assertFalse(item.ocr_available)
            self.assertEqual(item.raw_content["width"], 200)
            self.assertEqual(item.raw_content["height"], 100)
            self.assertEqual(item.raw_content["ocr_text"], "")
        finally:
            temp_img_path.unlink()

    def test_image_with_custom_ocr_runner(self):
        from PIL import Image
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as f:
            img = Image.new("RGB", (200, 100), color="white")
            img.save(f, format="PNG")
            temp_img_path = Path(f.name)

        try:
            # Custom mock OCR runner returning recognized text
            def mock_ocr(path: Path) -> str:
                return "Admin Console - User: ocr.target@example.com ID: user_ocr_99"

            items = self.manager.parse_image_file(
                file_id="evidence_img_ocr",
                image_path=temp_img_path,
                origin="admin_console",
                captured_at="2026-08-01T10:00:00Z",
                ocr_runner=mock_ocr,
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertTrue(item.ocr_available)
            self.assertIn("ocr.target@example.com", item.identifiers)
            self.assertIn("user_ocr_99", item.identifiers)
        finally:
            temp_img_path.unlink()

    def test_temporal_filtering_with_identifiers(self):
        # Create user identity
        test_user = UserIdentity(
            user_id="user_temporal_1",
            name="Temporal Tester",
            current_email="temporal.user@example.com",
            current_phone="+1 555-0100",
            current_email_hash="hash_temporal_123",
            updated_at="2026-05-01T00:00:00Z",
            historical_emails=["old.temporal@example.com"],
        )

        # Inject items directly into manager index for unit testing
        item_pre = EvidenceItem(
            evidence_id="evidence_pre",
            source_type="TEST",
            captured_at="2026-08-01T12:00:00Z",
            event_time="2026-08-01T12:00:00Z",
            system_id="account_service",
            resource_id="account_pre",
            state="PRESENT",
            identifiers={"temporal.user@example.com"},
        )
        item_post = EvidenceItem(
            evidence_id="evidence_post",
            source_type="TEST",
            captured_at="2026-09-20T12:00:00Z",
            event_time="2026-09-20T12:00:00Z",
            system_id="account_service",
            resource_id="account_post",
            state="PRESENT",
            identifiers={"old.temporal@example.com"},
        )

        mgr = EvidenceManager()
        mgr._is_loaded = True
        mgr._items = [item_pre, item_post]
        mgr._by_identifier = {
            "temporal.user@example.com": [item_pre],
            "old.temporal@example.com": [item_post],
        }

        # Query with cutoff between item_pre and item_post: 2026-09-01
        cutoff = "2026-09-01T00:00:00Z"
        results = mgr.get_evidence_for_user(test_user, cutoff=cutoff)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].evidence_id, "evidence_pre")
        self.assertEqual(results[0].resource_id, "account_pre")

        # Query with late cutoff: both should be returned
        late_cutoff = "2026-10-01T00:00:00Z"
        all_results = mgr.get_evidence_for_user(test_user, cutoff=late_cutoff)
        self.assertEqual(len(all_results), 2)

    def test_post_cutoff_capture_strictly_excluded(self):
        """Verify that an evidence item captured after audit_at cannot prove earlier state (§6.2, §6.6)."""
        tf = TemporalFilter("2026-09-15T12:00:00Z")
        # Event timestamp was earlier, but evidence file captured later -> MUST BE FALSE
        self.assertFalse(tf.is_eligible(event_time="2026-09-10T12:00:00Z", capture_time="2026-09-20T12:00:00Z"))
        # Both pre-cutoff -> True
        self.assertTrue(tf.is_eligible(event_time="2026-09-10T12:00:00Z", capture_time="2026-09-12T12:00:00Z"))

    def test_sql_replica_table_mappings(self):
        """Verify that regional and failover replica tables map to their authoritative systems."""
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
            f.write("""
            CREATE TABLE search_documents_primary (
                resource_id TEXT PRIMARY KEY,
                customer_reference TEXT,
                email TEXT
            );
            CREATE TABLE customer_data_replica_ap_south (
                resource_id TEXT PRIMARY KEY,
                customer_reference TEXT,
                email TEXT
            );
            INSERT INTO search_documents_primary VALUES ('search_rep_01', 'user_rep_1', 'rep@example.com');
            INSERT INTO customer_data_replica_ap_south VALUES ('account_rep_02', 'user_rep_1', 'rep@example.com');
            """)
            temp_path = Path(f.name)

        try:
            items = self.manager.parse_sql_file(
                file_id="evidence_replica_test",
                sql_path=temp_path,
                origin="account_service",
                captured_at="2026-09-01T00:00:00Z",
            )
            self.assertEqual(len(items), 2)
            sys_by_res = {item.resource_id: item.system_id for item in items}
            self.assertEqual(sys_by_res["search_rep_01"], "search_service")
            self.assertEqual(sys_by_res["account_rep_02"], "account_service")
        finally:
            temp_path.unlink()

    def test_tombstone_redacted_vs_exposed_parsing(self):
        """Verify that account tombstones preserve subject_reference and distinguish REDACTED vs PRESENT."""
        bundle_data = {
            "snapshots": [
                {
                    "captured_at": "2026-09-15T12:00:00Z",
                    "data_store": "identity_service",
                    "collection": "deleted_customer_references",
                    "records": [
                        {
                            "resource_id": "tombstone_clean",
                            "subject_reference": "user_clean_01",
                            "name": None,
                            "email": None,
                            "phone": None,
                            "email_hash": None,
                            "account_status": "DELETED",
                        },
                        {
                            "resource_id": "tombstone_exposed",
                            "subject_reference": "user_exposed_02",
                            "name": "Exposed Person",
                            "email": "exposed@example.com",
                            "phone": "+1 555-0199",
                            "email_hash": "abc",
                            "account_status": "DELETED",
                        },
                    ],
                }
            ]
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bundle_data, f)
            temp_json = Path(f.name)

        try:
            items = self.manager.parse_json_record_file(
                file_id="evidence_tombstone_test",
                json_path=temp_json,
                origin="identity_service",
                captured_at="2026-09-15T12:00:00Z",
            )
            self.assertEqual(len(items), 2)
            item_clean = next(i for i in items if i.resource_id == "tombstone_clean")
            self.assertEqual(item_clean.state, "REDACTED")
            self.assertIn("user_clean_01", item_clean.identifiers)
            self.assertEqual(item_clean.system_id, "identity_service")

            item_exposed = next(i for i in items if i.resource_id == "tombstone_exposed")
            self.assertEqual(item_exposed.state, "PRESENT")
            self.assertIn("user_exposed_02", item_exposed.identifiers)
            self.assertIn("exposed@example.com", item_exposed.identifiers)
        finally:
            temp_json.unlink()

    def test_image_ocr_resource_and_system_parsing(self):
        """Verify that OCR text extracts specific resource IDs and system mappings."""
        from PIL import Image
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as f:
            img = Image.new("RGB", (200, 100), color="white")
            img.save(f, format="PNG")
            temp_img = Path(f.name)

        try:
            def mock_admin_ocr(p: Path) -> str:
                return "Customer Operations - User: Haruka Sato account_5762 haruka.s1838@zoho.com +81 90 7610 2507"

            items = self.manager.parse_image_file(
                file_id="evidence_img_admin",
                image_path=temp_img,
                origin="account_admin_portal",
                captured_at="2026-09-26T11:00:00Z",
                ocr_runner=mock_admin_ocr,
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.resource_id, "account_5762")
            self.assertEqual(item.system_id, "account_service")
            self.assertIn("haruka.s1838@zoho.com", item.identifiers)
            self.assertIn("+81 90 7610 2507", item.identifiers)
        finally:
            temp_img.unlink()

    def test_user_audit_log_parsing(self):
        """Verify that user_audit_log.csv is ingested with audit_id citations."""
        audit_items = self.manager.parse_user_audit_log()
        self.assertGreater(len(audit_items), 100, "Should ingest all user audit log events")
        first = audit_items[0]
        self.assertTrue(first.evidence_id.startswith("audit_"), "Should preserve audit_id as evidence_id")
        self.assertEqual(first.system_id, "identity_service")
        self.assertIn("user_485", first.identifiers)


if __name__ == "__main__":
    unittest.main()
