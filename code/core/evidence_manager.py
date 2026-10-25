"""Evidence parsing, ingestion, and temporal indexing module for Ghost Data Still Exists.

Parses all participant-visible evidence formats:
- SQLite SQL point-in-time snapshots (isolated in-memory read-only workflow)
- PDF compliance documents, statements, and registers
- PNG screenshots (with robust OCR and graceful non-OCR fallback)
- Observability and service event logs
- JSON snapshot bundles, manifests, and ledgers
- Plain-text handover reports
- Global system_activity.csv and user_audit_log.csv

Preserves source evidence citations (file_id, activity_id, audit_id) and enforces
strict temporal filtering (<= audit_at).
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
from PIL import Image

try:
    from code.config import (
        DATASET_DIR,
        EVIDENCE_DIR,
        EVIDENCE_FILES_PATH,
        SYSTEM_ACTIVITY_PATH,
        USER_AUDIT_LOG_PATH,
    )
    from code.core.identity_resolver import UserIdentity
    from code.core.temporal_filter import TemporalFilter, parse_iso_timestamp, is_at_or_before
except (ImportError, ModuleNotFoundError):
    from config import (
        DATASET_DIR,
        EVIDENCE_DIR,
        EVIDENCE_FILES_PATH,
        SYSTEM_ACTIVITY_PATH,
        USER_AUDIT_LOG_PATH,
    )
    from core.identity_resolver import UserIdentity
    from core.temporal_filter import TemporalFilter, parse_iso_timestamp, is_at_or_before


# Optional PDF dependencies
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


@dataclass
class EvidenceItem:
    """A single discrete piece of evidence extracted from any participant-visible file."""
    evidence_id: str                      # file_id, activity_id, or audit_id
    source_type: str                      # SQL_SNAPSHOT, PDF_DOCUMENT, IMAGE, LOG, JSON_RECORD, etc.
    file_path: Optional[str] = None       # Relative path in dataset/evidence/
    origin: Optional[str] = None          # Origin service from evidence_files.csv
    captured_at: Optional[str] = None     # Capture timestamp from evidence manifest
    event_time: Optional[str] = None      # Event/row timestamp within the evidence
    system_id: str = ""                   # System name (account_service, search_service, etc.)
    resource_id: str = ""                 # Unique resource ID (account_001, search_052, etc.)
    record_type: Optional[str] = None     # USER_PROFILE, SEARCH_INDEX_ENTRY, etc.
    state: Optional[str] = None           # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, BLOCKED
    identifiers: Set[str] = field(default_factory=set)  # Set of emails, user_ids, phones, hashes
    raw_content: Any = None               # Raw dictionary or text line
    ocr_available: bool = True            # False if OCR fallback was used on an image

    def matches_user(self, user: UserIdentity) -> bool:
        """Check if this item references any of the user's current or historical identifiers."""
        if not self.identifiers:
            return False
        # Normalize identifiers for case-insensitive check
        item_idents = {i.lower() for i in self.identifiers if i}
        user_idents = {u.lower() for u in user.all_searchable_strings if u}
        return bool(item_idents.intersection(user_idents))


TABLE_SYSTEM_MAP: Dict[str, str] = {
    "customer_profiles": "account_service",
    "customer_profiles_primary": "account_service",
    "customer_profiles_failover_replica": "account_service",
    "customer_data_primary": "account_service",
    "customer_data_failover_replica": "account_service",
    "customer_data_read_replica": "account_service",
    "customer_data_regional_replicas": "account_service",
    "customer_data_replica_ap_south": "account_service",
    "customer_data_replica_eu_west": "account_service",
    "customer_data_reporting_replica": "account_service",
    "customer_search_documents": "search_service",
    "customer_search_primary": "search_service",
    "search_documents_primary": "search_service",
    "customer_analytics_profiles": "analytics_platform",
    "support_records": "support_platform",
    "customer_exports": "export_service",
    "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service",
}

# Image origin-to-system mapping
IMAGE_ORIGIN_SYSTEM_MAP: Dict[str, str] = {
    "account_admin_portal": "account_service",
    "search_index_admin": "search_service",
    "integration_admin": "integration_service",
    "analytics_platform": "analytics_platform",
    "export_service": "export_service",
    "support_platform": "support_platform",
    "backup_service": "backup_service",
    "security_service": "security_service",
    "identity_service": "identity_service",
    "marketing_platform": "marketing_service",
    "object_storage": "object_storage",
}

# Regex to extract key-value pairs from log lines (supports both key="val" and key=val)
LOG_KV_REGEX = re.compile(r'(\b[a-zA-Z_]+)=(?:"([^"]*)"|([^\s]+))')
LOG_TIMESTAMP_REGEX = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)')
LOG_TAG_REGEX = re.compile(r'\[([a-zA-Z_]+)\]')


class EvidenceManager:
    """Manages ingestion, extraction, and temporal querying of evidence files."""

    def __init__(self, dataset_dir: Optional[Path] = None) -> None:
        self.dataset_dir = dataset_dir or DATASET_DIR
        self.evidence_dir = self.dataset_dir / "evidence"
        self.manifest_path = self.dataset_dir / "evidence_files.csv"
        self.system_activity_path = self.dataset_dir / "system_activity.csv"
        self.audit_log_path = self.dataset_dir / "user_audit_log.csv"

        # Manifest lookup: file_id -> metadata dict
        self._manifest: Dict[str, Dict[str, Any]] = {}

        # All indexed evidence items
        self._items: List[EvidenceItem] = []
        self._by_identifier: Dict[str, List[EvidenceItem]] = {}
        self._by_resource: Dict[Tuple[str, str], List[EvidenceItem]] = {}
        self._by_evidence_id: Dict[str, List[EvidenceItem]] = {}
        self._is_loaded: bool = False

        # Load OCR cache if present
        self.ocr_cache_path = Path(__file__).resolve().parent / "ocr_cache.json"
        self._ocr_cache: Dict[str, str] = {}
        if self.ocr_cache_path.exists():
            try:
                with open(self.ocr_cache_path, "r", encoding="utf-8") as f:
                    self._ocr_cache = json.load(f)
            except Exception:
                self._ocr_cache = {}

    def _get_rel_path(self, path: Path) -> str:
        """Safely compute relative path to dataset_dir without raising ValueError."""
        try:
            return str(path.resolve().relative_to(self.dataset_dir.resolve())).replace("\\", "/")
        except (ValueError, TypeError):
            return str(path).replace("\\", "/")

    def load_manifest(self) -> None:
        """Load evidence_files.csv manifest."""
        if not self.manifest_path.exists():
            return
        df = pd.read_csv(self.manifest_path)
        for _, row in df.iterrows():
            file_id = str(row["file_id"]).strip()
            self._manifest[file_id] = {
                "file_id": file_id,
                "file_path": str(row["file_path"]).strip(),
                "origin": str(row["origin"]).strip(),
                "captured_at": str(row["captured_at"]).strip(),
            }

    def parse_sql_file(
        self,
        file_id: str,
        sql_path: Path,
        origin: str,
        captured_at: str,
    ) -> List[EvidenceItem]:
        """Execute SQL dump safely in SQLite in-memory and extract table records."""
        items: List[EvidenceItem] = []
        if not sql_path.exists():
            return items

        with open(sql_path, "r", encoding="utf-8", errors="replace") as f:
            sql_script = f.read()

        try:
            conn = sqlite3.connect(":memory:")
            conn.executescript(sql_script)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall() if r[0] != "snapshot_scope"]

            for table in tables:
                cursor.execute(f"PRAGMA table_info({table});")
                col_names = [col[1] for col in cursor.fetchall()]

                cursor.execute(f"SELECT * FROM {table};")
                rows = cursor.fetchall()

                system_id = TABLE_SYSTEM_MAP.get(table, "account_service")

                for row in rows:
                    row_dict = dict(zip(col_names, row))
                    resource_id = str(row_dict.get("resource_id", "")).strip()
                    if not resource_id:
                        continue

                    # If record is stored as record_json, unpack it
                    record_json = row_dict.get("record_json")
                    if record_json and isinstance(record_json, str):
                        try:
                            rec_data = json.loads(record_json)
                            if isinstance(rec_data, dict):
                                if "origin_system" in row_dict and row_dict["origin_system"]:
                                    system_id = row_dict["origin_system"]
                                elif "origin_system" in rec_data and rec_data["origin_system"]:
                                    system_id = rec_data["origin_system"]

                                doc = rec_data.get("document")
                                if isinstance(doc, dict):
                                    rec_data.update(doc)

                                for k, v in rec_data.items():
                                    if k not in row_dict or not row_dict[k]:
                                        row_dict[k] = v
                        except Exception:
                            pass

                    # Extract all possible identifiers
                    identifiers: Set[str] = set()
                    for col in ["user_id", "customer_reference", "subject_reference"]:
                        if col in row_dict and row_dict[col]:
                            identifiers.add(str(row_dict[col]).strip())

                    for col in ["email", "customer_email", "requester_email", "owner_email"]:
                        if col in row_dict and row_dict[col]:
                            identifiers.add(str(row_dict[col]).strip())

                    for col in ["phone", "requester_phone", "owner_phone"]:
                        if col in row_dict and row_dict[col]:
                            identifiers.add(str(row_dict[col]).strip())

                    for col in ["email_hash"]:
                        if col in row_dict and row_dict[col]:
                            identifiers.add(str(row_dict[col]).strip())

                    for col in ["full_name", "display_name", "requester_name"]:
                        if col in row_dict and row_dict[col]:
                            identifiers.add(str(row_dict[col]).strip())

                    event_time = row_dict.get("updated_at")
                    state = "PRESENT"
                    if "account_status" in row_dict:
                        st = str(row_dict["account_status"]).upper()
                        if st == "DELETED":
                            state = "ABSENT"
                    if "enabled" in row_dict:
                        state = "ACTIVE" if row_dict["enabled"] else "DISABLED"
                    if "restore_allowed" in row_dict:
                        state = "ACTIVE" if row_dict["restore_allowed"] else "BLOCKED"

                    item = EvidenceItem(
                        evidence_id=file_id,
                        source_type="SQL_SNAPSHOT",
                        file_path=self._get_rel_path(sql_path),
                        origin=origin,
                        captured_at=captured_at,
                        event_time=str(event_time) if event_time else captured_at,
                        system_id=system_id,
                        resource_id=resource_id,
                        record_type=table.upper(),
                        state=state,
                        identifiers=identifiers,
                        raw_content=row_dict,
                    )
                    items.append(item)

            conn.close()
        except Exception:
            # Safe isolation: if any individual script errors, continue gracefully
            pass

        return items

    def parse_pdf_file(
        self,
        file_id: str,
        pdf_path: Path,
        origin: str,
        captured_at: str,
    ) -> List[EvidenceItem]:
        """Extract text and entities from PDF documents."""
        items: List[EvidenceItem] = []
        if not pdf_path.exists():
            return items

        text = ""
        if HAS_PYMUPDF:
            try:
                doc = fitz.open(pdf_path)
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
            except Exception:
                text = ""

        if not text and HAS_PYPDF:
            try:
                reader = pypdf.PdfReader(pdf_path)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
            except Exception:
                text = ""

        # Scan text for identifiers and resources
        identifiers: Set[str] = set()
        # Find emails
        for m in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', text):
            identifiers.add(m.group(0))
        # Find user references: user_...
        for m in re.finditer(r'\buser_[\w-]+\b', text):
            identifiers.add(m.group(0))
        # Find phones
        for m in re.finditer(r'\+\d{1,3}[\s\d\(\)-]{7,}', text):
            identifiers.add(m.group(0).strip())

        # Determine resource_id if present
        res_match = re.search(r'\b(support_\d+|audit_record_\d+|account_\d+|export_\d+|statement\s+[A-Z0-9-]+)\b', text, re.IGNORECASE)
        resource_id = res_match.group(1).replace(" ", "_") if res_match else pdf_path.stem

        item = EvidenceItem(
            evidence_id=file_id,
            source_type="PDF_DOCUMENT",
            file_path=self._get_rel_path(pdf_path),
            origin=origin,
            captured_at=captured_at,
            event_time=captured_at,
            system_id="document_store",
            resource_id=resource_id,
            record_type="DOCUMENT",
            state="PRESENT",
            identifiers=identifiers,
            raw_content=text[:2000],
        )
        items.append(item)
        return items

    def parse_image_file(
        self,
        file_id: str,
        image_path: Path,
        origin: str,
        captured_at: str,
        ocr_runner: Optional[Callable[[Path], str]] = None,
    ) -> List[EvidenceItem]:
        """Parse image file with OCR when provided, with graceful tested fallback."""
        items: List[EvidenceItem] = []
        if not image_path.exists():
            return items

        ocr_text = ""
        ocr_available = False

        if ocr_runner is not None:
            try:
                ocr_text = ocr_runner(image_path)
                ocr_available = True
            except Exception:
                ocr_text = ""
                ocr_available = False
        elif image_path.name in self._ocr_cache:
            ocr_text = self._ocr_cache[image_path.name]
            ocr_available = True

        # Extract basic image metadata
        width, height = 0, 0
        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            pass

        identifiers: Set[str] = set()
        resource_id = image_path.stem
        system_id = IMAGE_ORIGIN_SYSTEM_MAP.get(origin, origin)
        state = "PRESENT"

        if ocr_text:
            # Extract specific resource IDs
            res_matches = re.findall(
                r'\b(account_\d+|search_\d+|support_\d+|analytics_\d+|data_flow_\d+|backup_\d+|export_\d+|marketing_\d+|audit_record_\d+|tombstone_\d+)\b',
                ocr_text,
                re.IGNORECASE,
            )
            if res_matches:
                resource_id = res_matches[0].lower()

            # Check if there is an explicit Selector or Owner field for connectors/views
            sel_match = re.search(r'\b(?:Selector|Owner)\s+([\w\.-]+@[\w\.-]+\.\w+)', ocr_text, re.IGNORECASE)
            if sel_match:
                identifiers.add(sel_match.group(1).strip())
            else:
                # Extract emails
                for m in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', ocr_text):
                    identifiers.add(m.group(0))

            # Extract user references: user_...
            for m in re.finditer(r'\buser_[\w-]+\b', ocr_text):
                identifiers.add(m.group(0))
            # Extract phones
            for m in re.finditer(r'\+\d{1,3}[\s\d\(\)-]{7,}', ocr_text):
                identifiers.add(m.group(0).strip())

            # State heuristics for image console views
            if "data_flow" in resource_id:
                state = "ACTIVE" if ("Continuous" in ocr_text or "Healthy" in ocr_text) else "DISABLED"
            elif "backup" in resource_id:
                state = "ACTIVE" if ("restored" in ocr_text or "Recovery Manager" in ocr_text) else "BLOCKED"

        item = EvidenceItem(
            evidence_id=file_id,
            source_type="IMAGE",
            file_path=self._get_rel_path(image_path),
            origin=origin,
            captured_at=captured_at,
            event_time=captured_at,
            system_id=system_id,
            resource_id=resource_id,
            record_type="SCREENSHOT",
            state=state,
            identifiers=identifiers,
            raw_content={"width": width, "height": height, "ocr_text": ocr_text},
            ocr_available=ocr_available,
        )
        items.append(item)
        return items

    def parse_log_file(
        self,
        file_id: str,
        log_path: Path,
        origin: str,
        captured_at: str,
    ) -> List[EvidenceItem]:
        """Parse structured logs into individual EvidenceItem events."""
        items: List[EvidenceItem] = []
        if not log_path.exists():
            return items

        # Two-pass parsing for logs: correlate identifiers by trace_id
        trace_identifiers: Dict[str, Set[str]] = {}
        raw_log_lines = []

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                ts_match = LOG_TIMESTAMP_REGEX.match(line)
                event_time = ts_match.group(1) if ts_match else captured_at

                kv_dict = {}
                if "{" in line and "}" in line:
                    try:
                        json_str = line[line.index("{"):line.rindex("}") + 1]
                        kv_dict = json.loads(json_str)
                    except Exception:
                        kv_dict = {}
                if not kv_dict:
                    for m in LOG_KV_REGEX.finditer(line):
                        k = m.group(1)
                        v = m.group(2) if m.group(2) is not None else m.group(3)
                        kv_dict[k] = v

                trace_id = kv_dict.get("trace_id", "")
                if trace_id:
                    if trace_id not in trace_identifiers:
                        trace_identifiers[trace_id] = set()
                    for key in ["lookup_key", "subject_key", "matched_value", "correlation_key", "subject_ref", "user_id"]:
                        val = kv_dict.get(key)
                        if val and val != "no direct identifier" and val != "null":
                            trace_identifiers[trace_id].add(str(val).strip())

                raw_log_lines.append((line, event_time, kv_dict))

        for line, event_time, kv_dict in raw_log_lines:
            event_name = kv_dict.get("event", "")
            if event_name.endswith("_started"):
                continue

            tags = LOG_TAG_REGEX.findall(line)
            if "service" in kv_dict and kv_dict["service"]:
                system_id = kv_dict["service"]
            else:
                system_id = tags[1] if len(tags) > 1 else (tags[0] if tags else origin)

            resource_id = kv_dict.get("resource_id", "")
            if not resource_id:
                continue

            identifiers: Set[str] = set()
            for key in ["lookup_key", "subject_key", "matched_value", "correlation_key", "subject_ref", "user_id"]:
                val = kv_dict.get(key)
                if val and val != "no direct identifier":
                    identifiers.add(val.strip())

            trace_id = kv_dict.get("trace_id", "")
            if trace_id and trace_id in trace_identifiers:
                identifiers.update(trace_identifiers[trace_id])

            state = "PRESENT"
            if kv_dict.get("rows") == "0" or kv_dict.get("http_status") == "404" or kv_dict.get("result") == "miss":
                state = "ABSENT"
            elif kv_dict.get("result") == "hit" or kv_dict.get("rows") == "1":
                state = "PRESENT"
            elif system_id == "analytics_platform":
                is_attributable = any(kv_dict.get(k) and kv_dict[k] != "null" for k in ["email", "customer_reference", "user_id"])
                state = "PRESENT" if is_attributable else "ANONYMIZED"

            item = EvidenceItem(
                evidence_id=file_id,
                source_type="LOG",
                file_path=self._get_rel_path(log_path),
                origin=origin,
                captured_at=captured_at,
                event_time=event_time,
                system_id=system_id,
                resource_id=resource_id,
                record_type="LOG_EVENT",
                state=state,
                identifiers=identifiers,
                raw_content=line,
            )
            items.append(item)

        return items

    def parse_json_record_file(
        self,
        file_id: str,
        json_path: Path,
        origin: str,
        captured_at: str,
    ) -> List[EvidenceItem]:
        """Parse JSON snapshot bundles, manifests, and connector configurations."""
        items: List[EvidenceItem] = []
        if not json_path.exists():
            return items

        try:
            with open(json_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception:
            return items

        # 1. Snapshot bundle structure
        if "snapshots" in data and isinstance(data["snapshots"], list):
            for snapshot in data["snapshots"]:
                snap_time = snapshot.get("captured_at", captured_at)
                system_id = snapshot.get("data_store", origin)
                records = snapshot.get("records", [])

                for rec in records:
                    resource_id = rec.get("resource_id", "")
                    if not resource_id:
                        continue

                    identifiers: Set[str] = set()
                    for k in [
                        "customer_reference",
                        "subject_reference",
                        "user_id",
                        "email",
                        "phone",
                        "email_hash",
                        "full_name",
                        "name",
                        "owner",
                    ]:
                        if rec.get(k):
                            identifiers.add(str(rec[k]).strip())

                    # Nested documents
                    doc = rec.get("document", {})
                    if isinstance(doc, dict):
                        for k, v in doc.items():
                            if v:
                                identifiers.add(str(v).strip())

                    state = "PRESENT"
                    record_type = snapshot.get("collection", "SNAPSHOT_RECORD").upper()
                    if "tombstone" in resource_id:
                        record_type = "ACCOUNT_TOMBSTONE"
                        # Tombstone is REDACTED if direct PII is absent, else PRESENT (unredacted PII)
                        has_pii = any(rec.get(k) for k in ["name", "email", "phone", "email_hash"])
                        state = "PRESENT" if has_pii else "REDACTED"
                    elif "account_status" in rec:
                        if str(rec["account_status"]).upper() == "DELETED":
                            state = "ABSENT"

                    item = EvidenceItem(
                        evidence_id=file_id,
                        source_type="JSON_RECORD",
                        file_path=self._get_rel_path(json_path),
                        origin=origin,
                        captured_at=captured_at,
                        event_time=snap_time,
                        system_id=system_id,
                        resource_id=resource_id,
                        record_type=record_type,
                        state=state,
                        identifiers=identifiers,
                        raw_content=rec,
                    )
                    items.append(item)

        # 2. Flat records array (e.g. connector configurations, export jobs)
        elif "records" in data and isinstance(data["records"], list):
            for rec in data["records"]:
                resource_id = rec.get("resource_id", "")
                if not resource_id:
                    continue

                system_id = rec.get("system", origin)
                if resource_id.startswith("export_") or "export" in str(data.get("source", "")).lower() or "export" in str(data.get("collection", "")).lower():
                    system_id = "export_service"

                identifiers: Set[str] = set()
                for k in [
                    "customer_reference",
                    "subject_reference",
                    "user_id",
                    "email",
                    "owner_email",
                    "customer_email",
                    "requester_email",
                    "phone",
                    "email_hash",
                    "owner",
                ]:
                    if rec.get(k):
                        identifiers.add(str(rec[k]).strip())

                state = "PRESENT"
                if "download_available" in rec:
                    state = "PRESENT" if rec["download_available"] else "ABSENT"
                elif "enabled" in rec:
                    state = "ACTIVE" if rec.get("enabled", True) else "DISABLED"

                item = EvidenceItem(
                    evidence_id=file_id,
                    source_type="JSON_RECORD",
                    file_path=self._get_rel_path(json_path),
                    origin=origin,
                    captured_at=captured_at,
                    event_time=rec.get("recorded_at", rec.get("created_at", captured_at)),
                    system_id=system_id,
                    resource_id=resource_id,
                    record_type=rec.get("record_type", "CONFIG_RECORD"),
                    state=state,
                    identifiers=identifiers,
                    raw_content=rec,
                )
                items.append(item)

        # 3. Service resource export structure (e.g. service_resource_export_*.json)
        elif "service_exports" in data and isinstance(data["service_exports"], dict):
            for system_id, svc_data in data["service_exports"].items():
                if not isinstance(svc_data, dict):
                    continue
                for collection_name, records in svc_data.items():
                    if not isinstance(records, list):
                        continue
                    for rec in records:
                        if not isinstance(rec, dict):
                            continue
                        resource_id = rec.get("resource_id", "")
                        if not resource_id:
                            continue

                        obs_time = rec.get("observed_at", captured_at)
                        identifiers: Set[str] = set()

                        for k in [
                            "customer_reference",
                            "subject_reference",
                            "user_id",
                            "customer_email",
                            "owner_email",
                            "requester_email",
                            "email",
                            "customer_phone",
                            "owner_phone",
                            "requester_phone",
                            "phone",
                            "email_hash",
                            "customer_name",
                            "requester_name",
                            "display_name",
                            "query",
                        ]:
                            if rec.get(k):
                                identifiers.add(str(rec[k]).strip())

                        # Check nested profile if present
                        prof = rec.get("profile")
                        if isinstance(prof, dict):
                            for k in ["customer_reference", "email", "phone", "email_hash", "full_name"]:
                                if prof.get(k):
                                    identifiers.add(str(prof[k]).strip())

                        # Check hits.documents if present (search_service)
                        hits = rec.get("hits")
                        if isinstance(hits, dict):
                            for doc in hits.get("documents", []):
                                if isinstance(doc, dict):
                                    for k in ["customer_reference", "email", "phone", "email_hash", "display_name"]:
                                        if doc.get(k):
                                            identifiers.add(str(doc[k]).strip())

                        # State determination
                        state = "PRESENT"
                        if "status_code" in rec:
                            state = "ABSENT" if rec["status_code"] == 404 else "PRESENT"
                        elif "enabled" in rec:
                            state = "ACTIVE" if rec["enabled"] else "DISABLED"
                        elif "restore_allowed" in rec:
                            state = "ACTIVE" if rec["restore_allowed"] else "BLOCKED"
                        elif "hits" in rec:
                            state = "PRESENT" if rec["hits"].get("total", 0) > 0 else "ABSENT"
                        elif system_id == "analytics_platform":
                            # If email and customer_reference are absent/null -> ANONYMIZED
                            is_attributable = any(rec.get(k) for k in ["email", "customer_reference", "user_id"])
                            state = "PRESENT" if is_attributable else "ANONYMIZED"
                        elif system_id == "support_platform":
                            # If requester_email is absent/null -> REDACTED
                            is_exposed = any(rec.get(k) for k in ["requester_email", "customer_email", "email", "requester_phone"])
                            state = "PRESENT" if is_exposed else "REDACTED"
                        elif system_id == "security_service":
                            state = "PRESENT"

                        item = EvidenceItem(
                            evidence_id=file_id,
                            source_type="SERVICE_EXPORT",
                            file_path=self._get_rel_path(json_path),
                            origin=origin,
                            captured_at=obs_time,
                            event_time=obs_time,
                            system_id=system_id,
                            resource_id=resource_id,
                            record_type=collection_name.upper(),
                            state=state,
                            identifiers=identifiers,
                            raw_content=rec,
                        )
                        items.append(item)

        return items

    def parse_txt_record_file(
        self,
        file_id: str,
        txt_path: Path,
        origin: str,
        captured_at: str,
    ) -> List[EvidenceItem]:
        """Parse shift handover and text reports."""
        items: List[EvidenceItem] = []
        if not txt_path.exists():
            return items

        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- "):
                    parts = [p.strip() for p in line[2:].split("|")]
                    if len(parts) >= 6:
                        ev_time, sys_id, res_id, cat, raw_state, target = (
                            parts[0],
                            parts[1],
                            parts[2],
                            parts[3],
                            parts[4],
                            parts[5],
                        )

                        identifiers: Set[str] = set()
                        if target != "no direct identifier":
                            identifiers.add(target)

                        # Map raw state to standard state
                        state = "PRESENT"
                        if raw_state == "NOT_FOUND":
                            state = "ABSENT"
                        elif raw_state == "REDACTED":
                            state = "REDACTED"
                        elif raw_state == "ANONYMIZED":
                            state = "ANONYMIZED"
                        elif raw_state == "BLOCKED":
                            state = "BLOCKED"
                        elif raw_state == "DISABLED":
                            state = "DISABLED"
                        elif raw_state == "ACTIVE":
                            state = "ACTIVE"

                        item = EvidenceItem(
                            evidence_id=file_id,
                            source_type="TXT_RECORD",
                            file_path=self._get_rel_path(txt_path),
                            origin=origin,
                            captured_at=captured_at,
                            event_time=ev_time,
                            system_id=sys_id,
                            resource_id=res_id,
                            record_type=cat,
                            state=state,
                            identifiers=identifiers,
                            raw_content=line,
                        )
                        items.append(item)

        return items

    def parse_system_activity(self) -> List[EvidenceItem]:
        """Ingest system_activity.csv as discrete Activity EvidenceItems."""
        items: List[EvidenceItem] = []
        if not self.system_activity_path.exists():
            return items

        df = pd.read_csv(self.system_activity_path)
        for _, row in df.iterrows():
            act_id = str(row["activity_id"]).strip()
            ev_time = str(row["event_time"]).strip()
            source_sys = str(row["source_system"]).strip()
            target_sys = str(row["target_system"]).strip()
            res_id = str(row["resource_id"]).strip()
            res_val = str(row["reported_result"]).strip().upper()
            details = str(row["details"]).strip()

            identifiers: Set[str] = set()
            for m in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', details):
                identifiers.add(m.group(0))
            for m in re.finditer(r'user_\d+', details):
                identifiers.add(m.group(0))

            ev_type = str(row["event_type"]).strip().upper()
            if ev_type == "LINK_RESOURCE_IDENTITY":
                continue
            state = "PRESENT"
            if res_val == "SUCCESS":
                if ev_type == "DELETE_RECORD":
                    state = "ABSENT"
                elif ev_type == "DISABLE_DATA_FLOW":
                    state = "DISABLED"
                elif ev_type == "BLOCK_RESTORE":
                    state = "BLOCKED"
                elif ev_type == "ANONYMIZE_RECORD":
                    state = "ANONYMIZED"
                elif ev_type == "REDACT_RECORD":
                    state = "REDACTED"
                else:
                    state = "PRESENT"
            elif res_val in ("FAILED", "ERROR"):
                if ev_type in ("DISABLE_DATA_FLOW", "BLOCK_RESTORE", "CHECK_DATA_FLOW"):
                    state = "ACTIVE"
                else:
                    state = "PRESENT"

            item = EvidenceItem(
                evidence_id=act_id,
                source_type="SYSTEM_ACTIVITY",
                captured_at=ev_time,
                event_time=ev_time,
                system_id=target_sys or source_sys,
                resource_id=res_id,
                record_type=str(row["event_type"]).strip(),
                state=state,
                identifiers=identifiers,
                raw_content=details,
            )
            items.append(item)

        return items

    def parse_user_audit_log(self) -> List[EvidenceItem]:
        """Ingest user_audit_log.csv as discrete audit EvidenceItems."""
        items: List[EvidenceItem] = []
        if not self.audit_log_path.exists():
            return items

        df = pd.read_csv(self.audit_log_path)
        for _, row in df.iterrows():
            audit_id = str(row["audit_id"]).strip()
            user_id = str(row["user_id"]).strip()
            ev_time = str(row["event_time"]).strip()
            field_name = str(row["field_name"]).strip()
            old_val = str(row["old_value"]).strip()
            new_val = str(row["new_value"]).strip()

            identifiers: Set[str] = {user_id}
            if old_val:
                identifiers.add(old_val)
            if new_val:
                identifiers.add(new_val)

            item = EvidenceItem(
                evidence_id=audit_id,
                source_type="USER_AUDIT_LOG",
                captured_at=ev_time,
                event_time=ev_time,
                system_id="identity_service",
                resource_id=f"audit_{audit_id}",
                record_type=f"IDENTITY_CHANGE_{field_name.upper()}",
                state="PRESENT",
                identifiers=identifiers,
                raw_content=dict(row),
            )
            items.append(item)

        return items

    def load_all_evidence(self) -> None:
        """Parse and index all files in evidence_files.csv, system_activity, and audit log."""
        if self._is_loaded:
            return

        self.load_manifest()

        # Parse each file registered in manifest
        for file_id, meta in self._manifest.items():
            rel_path = meta["file_path"]
            full_path = self.dataset_dir / rel_path
            origin = meta["origin"]
            captured_at = meta["captured_at"]

            ext = full_path.suffix.lower()
            if ext == ".sql":
                items = self.parse_sql_file(file_id, full_path, origin, captured_at)
            elif ext == ".pdf":
                items = self.parse_pdf_file(file_id, full_path, origin, captured_at)
            elif ext == ".png":
                items = self.parse_image_file(file_id, full_path, origin, captured_at)
            elif ext == ".log":
                items = self.parse_log_file(file_id, full_path, origin, captured_at)
            elif ext == ".json":
                items = self.parse_json_record_file(file_id, full_path, origin, captured_at)
            elif ext == ".txt":
                items = self.parse_txt_record_file(file_id, full_path, origin, captured_at)
            else:
                items = []

            self._items.extend(items)

        # Ingest system activity
        activity_items = self.parse_system_activity()
        self._items.extend(activity_items)

        # Ingest user audit log
        audit_items = self.parse_user_audit_log()
        self._items.extend(audit_items)

        # Index all items
        for item in self._items:
            # By evidence_id
            if item.evidence_id not in self._by_evidence_id:
                self._by_evidence_id[item.evidence_id] = []
            self._by_evidence_id[item.evidence_id].append(item)

            # By resource (system_id, resource_id)
            key = (item.system_id, item.resource_id)
            if key not in self._by_resource:
                self._by_resource[key] = []
            self._by_resource[key].append(item)

            # By identifier (lowercased)
            for ident in item.identifiers:
                clean_ident = ident.strip().lower()
                if clean_ident not in self._by_identifier:
                    self._by_identifier[clean_ident] = []
                self._by_identifier[clean_ident].append(item)

        self._is_loaded = True

    def get_evidence_for_identifiers(
        self,
        identifiers: Set[str],
        cutoff: Optional[Union[str, TemporalFilter]] = None,
    ) -> List[EvidenceItem]:
        """Query all evidence items matching any of the identifiers at or before cutoff."""
        if not self._is_loaded:
            self.load_all_evidence()

        temporal_filter = None
        if cutoff is not None:
            if isinstance(cutoff, TemporalFilter):
                temporal_filter = cutoff
            else:
                temporal_filter = TemporalFilter(cutoff)

        seen_item_keys: Set[Tuple[str, str, str]] = set()
        results: List[EvidenceItem] = []

        for ident in identifiers:
            clean = ident.strip().lower()
            for item in self._by_identifier.get(clean, []):
                item_key = (item.evidence_id, item.system_id, item.resource_id, item.event_time)
                if item_key in seen_item_keys:
                    continue

                if temporal_filter:
                    if not temporal_filter.is_eligible(
                        event_time=item.event_time,
                        capture_time=item.captured_at,
                    ):
                        continue

                seen_item_keys.add(item_key)
                results.append(item)

        # Pass 2: Retrieve all lifecycle items for discovered user resources
        # e.g. subsequent readback checks, lookups, or replica states for the user's resources
        discovered_resources = {(it.system_id, it.resource_id) for it in results if it.resource_id}
        for res_key in discovered_resources:
            for item in self._by_resource.get(res_key, []):
                item_key = (item.evidence_id, item.system_id, item.resource_id, item.event_time)
                if item_key in seen_item_keys:
                    continue

                if temporal_filter:
                    if not temporal_filter.is_eligible(
                        event_time=item.event_time,
                        capture_time=item.captured_at,
                    ):
                        continue

                seen_item_keys.add(item_key)
                results.append(item)

        return results

    def get_evidence_for_user(
        self,
        user: UserIdentity,
        cutoff: Optional[Union[str, TemporalFilter]] = None,
    ) -> List[EvidenceItem]:
        """Convenience method to query all evidence for a UserIdentity."""
        return self.get_evidence_for_identifiers(user.all_searchable_strings, cutoff=cutoff)
