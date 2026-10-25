"""Central configuration, file paths, and constants for Ghost Data Still Exists.

All paths are resolved relative to the repository root to ensure portability
across operating systems, environments, and checkouts.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, List, Set


# Base repository directories
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
CODE_DIR: Path = REPO_ROOT / "code"
DATASET_DIR: Path = REPO_ROOT / "dataset"
EVIDENCE_DIR: Path = DATASET_DIR / "evidence"
EVALUATION_DIR: Path = CODE_DIR / "evaluation"

# Key participant-facing files
DELETION_REQUESTS_PATH: Path = DATASET_DIR / "deletion_requests.csv"
SAMPLE_DELETION_REQUESTS_PATH: Path = DATASET_DIR / "sample_deletion_requests.csv"
SAMPLE_OUTPUT_PATH: Path = DATASET_DIR / "sample_output.csv"
USER_IDENTITIES_PATH: Path = DATASET_DIR / "user_identities.csv"
USER_AUDIT_LOG_PATH: Path = DATASET_DIR / "user_audit_log.csv"
SYSTEM_ACTIVITY_PATH: Path = DATASET_DIR / "system_activity.csv"
DELETION_RULES_PATH: Path = DATASET_DIR / "deletion_rules.csv"
EVIDENCE_FILES_PATH: Path = DATASET_DIR / "evidence_files.csv"
OUTPUT_PATH: Path = REPO_ROOT / "output.csv"

# Evidence subdirectories
EVIDENCE_DATABASES_DIR: Path = EVIDENCE_DIR / "databases"
EVIDENCE_DOCUMENTS_DIR: Path = EVIDENCE_DIR / "documents"
EVIDENCE_IMAGES_DIR: Path = EVIDENCE_DIR / "images"
EVIDENCE_LOGS_DIR: Path = EVIDENCE_DIR / "logs"
EVIDENCE_RECORDS_DIR: Path = EVIDENCE_DIR / "records"

# Challenge constraints
EVALUATION_REQUEST_COUNT: int = 518
SAMPLE_REQUEST_COUNT: int = 32


class DeletionStatus(str, Enum):
    """Overall audit decision for a deletion request."""
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Phase(str, Enum):
    """Step phases in their strict required execution order."""
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


PHASE_ORDER: List[str] = [
    Phase.FINDING.value,
    Phase.REMEDIATION.value,
    Phase.VERIFICATION.value,
]


class Operation(str, Enum):
    """Allowed step operations according to the problem statement contract."""
    # Findings
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"

    # Remediation
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    ANONYMIZE = "ANONYMIZE_RECORD"

    # Verification
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class State(str, Enum):
    """Allowed states corresponding to step operations."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


# Operation-to-state mapping contract
OPERATION_STATE_MAP: Dict[str, str] = {
    # Findings
    Operation.REPORT_REMAINING_RECORD.value: State.PRESENT.value,
    Operation.REPORT_EXPOSED_PII.value: State.PRESENT.value,
    Operation.REPORT_ACTIVE_DATA_FLOW.value: State.ACTIVE.value,
    Operation.REPORT_RESTORE_RISK.value: State.ACTIVE.value,

    # Remediation
    Operation.DISABLE_DATA_FLOW.value: State.DISABLED.value,
    Operation.BLOCK_RESTORE.value: State.BLOCKED.value,
    Operation.DELETE_RECORD.value: State.ABSENT.value,
    Operation.REDACT_RECORD.value: State.REDACTED.value,
    "ANONYMIZE_RECORD": State.ANONYMIZED.value,

    # Verification
    Operation.VERIFY_RECORD_ABSENT.value: State.ABSENT.value,
    Operation.VERIFY_RECORD_PRESENT.value: State.PRESENT.value,
    Operation.VERIFY_RECORD_REDACTED.value: State.REDACTED.value,
    Operation.VERIFY_RECORD_ANONYMIZED.value: State.ANONYMIZED.value,
    Operation.VERIFY_DATA_FLOW_DISABLED.value: State.DISABLED.value,
    Operation.VERIFY_RESTORE_BLOCKED.value: State.BLOCKED.value,
}

# Strict operation order within each phase as defined in problem_statement.md § Allowed Operations
OPERATION_ORDER: Dict[str, List[str]] = {
    Phase.FINDING.value: [
        "REPORT_REMAINING_RECORD",
        "REPORT_EXPOSED_PII",
        "REPORT_ACTIVE_DATA_FLOW",
        "REPORT_RESTORE_RISK",
    ],
    Phase.REMEDIATION.value: [
        "DISABLE_DATA_FLOW",
        "BLOCK_RESTORE",
        "DELETE_RECORD",
        "REDACT_RECORD",
        "ANONYMIZE_RECORD",
    ],
    Phase.VERIFICATION.value: [
        "VERIFY_RECORD_ABSENT",
        "VERIFY_RECORD_PRESENT",
        "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED",
        "VERIFY_RESTORE_BLOCKED",
    ],
}


class DeletionRuleAction(str, Enum):
    """Actions defined in deletion_rules.csv."""
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"
