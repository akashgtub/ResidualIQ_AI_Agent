"""Intent classification module for Ghost Data Still Exists.

Determines whether a user request_text explicitly authorizes account deletion or
represents a non-deletion action (e.g. data access, correction, export, or marketing
opt-out) which must be marked NOT_APPLICABLE under problem statement §6.5.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import List, Optional, Tuple


class RequestType(str, Enum):
    """Categorization of incoming privacy / data subject requests."""
    DELETION = "DELETION"
    ACCESS = "ACCESS"
    CORRECTION = "CORRECTION"
    EXPORT = "EXPORT"
    MARKETING_OPT_OUT = "MARKETING_OPT_OUT"
    LOGIN_SUPPORT = "LOGIN_SUPPORT"
    OTHER_NON_DELETION = "OTHER_NON_DELETION"


@dataclass
class RequestIntent:
    """Classification outcome for request_text."""
    is_deletion: bool
    request_type: RequestType
    matched_patterns: List[str]
    explanation: str


# Expressions indicating that the request is NOT a deletion request or explicitly retains data
EXPLICIT_NON_DELETION_RULES: List[Tuple[str, RequestType, str]] = [
    # 1. Marketing opt-out / promotional emails
    (
        r"\bmarketing\s+lists?\s+only\b",
        RequestType.MARKETING_OPT_OUT,
        "Request targets marketing lists only while preserving account",
    ),
    (
        r"\bstop\s+(?:the\s+)?promotional\s+emails?\b",
        RequestType.MARKETING_OPT_OUT,
        "Request to stop promotional emails while keeping account",
    ),
    (
        r"\bunsubscribe\s+from\s+(?:promotional|marketing)\b",
        RequestType.MARKETING_OPT_OUT,
        "Request to unsubscribe from marketing emails",
    ),

    # 2. Access / Information request
    (
        r"\binformation\s+request\b",
        RequestType.ACCESS,
        "Explicitly identified as an information / access request",
    ),
    (
        r"\bwhat\s+personal\s+information\s+you\s+hold\b",
        RequestType.ACCESS,
        "Request asking what personal information is held",
    ),
    (
        r"\bcopy\s+of\s+(?:last\s+year[\'’]s\s+invoices|the\s+information\s+held)\b",
        RequestType.ACCESS,
        "Request for copy of invoices or held information",
    ),

    # 3. Data Export / Portability
    (
        r"\bdownload\s+my\s+account\s+information\b",
        RequestType.EXPORT,
        "Data portability / download request",
    ),
    (
        r"\bportable\s+format\b",
        RequestType.EXPORT,
        "Data portability export request",
    ),

    # 4. Correction / Rectification
    (
        r"\bmisspelled\b",
        RequestType.CORRECTION,
        "Correction of misspelled name or field",
    ),
    (
        r"\breplace\s+it\s+with\s+the\s+new\s+one\b",
        RequestType.CORRECTION,
        "Replacement / update of contact information",
    ),
    (
        r"\bchange\s+the\s+email\s+address\s+used\s+for\s+this\s+account\b",
        RequestType.CORRECTION,
        "Request to change account email while continuing service",
    ),
    (
        r"\bwithout\s+removing\s+(?:any\s+of\s+my\s+)?records\b",
        RequestType.CORRECTION,
        "User requests correction without removing records",
    ),

    # 5. Login Support
    (
        r"\baccess\s+my\s+profile\s+and\s+need\s+help\s+resetting\b",
        RequestType.LOGIN_SUPPORT,
        "Login reset support request",
    ),

    # 6. Explicit disclaimers and retention instructions (Generic)
    (
        r"\bnot\s+(?:asking\s+for|a\s+request\s+to\s+(?:erase|delete|close))\b",
        RequestType.OTHER_NON_DELETION,
        "User explicitly states they are not asking for deletion or erasure",
    ),
    (
        r"\b(?:do\s+not|don[\'’]t)\s+(?:delete|close|erase)\b",
        RequestType.OTHER_NON_DELETION,
        "User explicitly commands not to delete or close the account",
    ),
    (
        r"\b(?:leave|keep)\s+(?:the|my)\s+(?:account|profile|purchase\s+history|records)\s+(?:active|as\s+it\s+is|in\s+place)\b",
        RequestType.OTHER_NON_DELETION,
        "User requests to leave or keep the account/profile active or in place",
    ),
    (
        r"\bcontinue\s+using\s+(?:the\s+service|my\s+account|this\s+service)\b",
        RequestType.OTHER_NON_DELETION,
        "User explicitly states intention to continue using the service",
    ),
    (
        r"\bstill\s+(?:use\s+it|need\s+the\s+account)\b",
        RequestType.OTHER_NON_DELETION,
        "User states they still use or need the account",
    ),
]


# Patterns authorizing deletion across supported languages
DELETION_PATTERNS: List[Tuple[str, str]] = [
    # English deletion phrases
    (r"\b(?:permanent(?:ly)?\s+)?(?:account\s+)?delet(?:e|ed|ing|ion)\b", "English delete/deletion"),
    (r"\baccount-deletion\b", "English account-deletion"),
    (r"\b(?:permanent(?:ly)?\s+)?eras(?:e|ed|ing|ure)\b", "English erase/erasure"),
    (r"\bclose\s+(?:this|my|the)\s+account\b", "English close account"),
    (r"\baccount\s+(?:is|was)\s+closed\b", "English closed account follow-up"),
    (r"\bremove\s+(?:the|my|this|any|that|records)\b", "English remove records/profile"),
    (r"\b(?:remov(?:ed|al))\b", "English removed/removal"),
    (r"\bde-identification\b", "English de-identification"),
    (r"\bpurging\b", "English purging"),
    (r"\bprofile\s+is\s+gone\b", "English profile is gone follow-up"),
    (r"\baccount\s+page\s+is\s+gone\b", "English account page is gone follow-up"),
    (r"\bsearch\s+result\s+(?:can\s+)?still\s+be\s+found\b", "English lingering search result audit"),
    # French
    (r"\bsuppression\b", "French suppression"),
    (r"\bsupprimer\b", "French supprimer"),
    (r"\beffacer\b", "French effacer"),
    # Spanish
    (r"\beliminaci[oó]n\b", "Spanish eliminación"),
    (r"\beliminar\b", "Spanish eliminar"),
    (r"\bborrar\b", "Spanish borrar"),
    # Portuguese
    (r"\bexclus[aã]o\b", "Portuguese exclusão"),
    (r"\bexcluir\b", "Portuguese excluir"),
    (r"\bapagar\b", "Portuguese apagar"),
    # Japanese
    (r"削除", "Japanese 削除 (sakujo - delete)"),
    (r"消去", "Japanese 消去 (shoukyo - erase)"),
    # Korean
    (r"삭제", "Korean 삭제 (sakje - delete)"),
    # German
    (r"\bl[oö]sch", "German löschen/Löschung"),
    # Italian
    (r"\bcancell", "Italian cancellare/cancellazione"),
]


class IntentClassifier:
    """Classifies user request text into deletion vs. non-deletion intent."""

    def __init__(self) -> None:
        self._non_deletion_rules = [
            (re.compile(pat, re.IGNORECASE), req_type, desc)
            for pat, req_type, desc in EXPLICIT_NON_DELETION_RULES
        ]
        self._deletion_rules = [
            (re.compile(pat, re.IGNORECASE), desc)
            for pat, desc in DELETION_PATTERNS
        ]

    def classify(self, text: Optional[str]) -> RequestIntent:
        """Classify request_text into a structured RequestIntent."""
        if not text or not isinstance(text, str) or not text.strip():
            return RequestIntent(
                is_deletion=False,
                request_type=RequestType.OTHER_NON_DELETION,
                matched_patterns=[],
                explanation="Empty or missing request text",
            )

        cleaned_text = text.strip()

        # Phase 1: Check explicit non-deletion rules (overrides deletion keywords)
        matched_non_del = []
        for regex, req_type, desc in self._non_deletion_rules:
            if regex.search(cleaned_text):
                matched_non_del.append((req_type, desc))

        if matched_non_del:
            req_type, desc = matched_non_del[0]
            return RequestIntent(
                is_deletion=False,
                request_type=req_type,
                matched_patterns=[d for _, d in matched_non_del],
                explanation=f"Non-deletion intent detected: {desc}",
            )

        # Phase 2: Check for affirmative deletion authorization
        matched_del = []
        for regex, desc in self._deletion_rules:
            if regex.search(cleaned_text):
                matched_del.append(desc)

        if matched_del:
            return RequestIntent(
                is_deletion=True,
                request_type=RequestType.DELETION,
                matched_patterns=matched_del,
                explanation=f"Deletion authorized by {matched_del[0]}",
            )

        # Phase 3: Conservative default - if no deletion pattern matches, treat as non-deletion
        return RequestIntent(
            is_deletion=False,
            request_type=RequestType.OTHER_NON_DELETION,
            matched_patterns=[],
            explanation="No recognized deletion authorization keywords found",
        )

    def is_deletion_authorized(self, text: Optional[str]) -> bool:
        """Convenience helper returning True only if request authorizes deletion."""
        return self.classify(text).is_deletion
