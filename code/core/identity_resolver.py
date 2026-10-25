"""Identity resolution module for Ghost Data Still Exists.

Reconstructs current and historical user identities by joining user_identities.csv
with user_audit_log.csv. Normalizes emails case-insensitively while preserving
all historical emails, phone numbers, and hashes.
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd

try:
    from code.config import USER_IDENTITIES_PATH, USER_AUDIT_LOG_PATH
except (ImportError, ModuleNotFoundError):
    from config import USER_IDENTITIES_PATH, USER_AUDIT_LOG_PATH


@dataclass
class IdentityAuditEvent:
    """Historical identity change event from user_audit_log.csv."""
    audit_id: str
    user_id: str
    event_time: str
    field_name: str
    old_value: str
    new_value: str


@dataclass
class UserIdentity:
    """Resolved identity containing both current snapshot and historical identifiers."""
    user_id: str
    name: str
    current_email: str
    current_phone: str
    current_email_hash: str
    updated_at: str
    historical_emails: List[str] = field(default_factory=list)
    historical_phones: List[str] = field(default_factory=list)
    historical_email_hashes: List[str] = field(default_factory=list)
    audit_events: List[IdentityAuditEvent] = field(default_factory=list)

    @property
    def all_emails(self) -> Set[str]:
        """Set of all current and historical emails (lowercased)."""
        emails = {self.current_email.lower()}
        for em in self.historical_emails:
            emails.add(em.lower())
        return emails

    @property
    def all_phones(self) -> Set[str]:
        """Set of all current and historical phone numbers."""
        phones = {self.current_phone}
        for ph in self.historical_phones:
            phones.add(ph)
        return phones

    @property
    def all_email_hashes(self) -> Set[str]:
        """Set of all current and historical SHA-256 email hashes (lowercased)."""
        hashes = {self.current_email_hash.lower()}
        for h in self.historical_email_hashes:
            hashes.add(h.lower())
        return hashes

    @property
    def all_searchable_strings(self) -> Set[str]:
        """All string tokens associated with this user across current and historical data."""
        tokens: Set[str] = {
            self.user_id,
            self.name,
            self.current_email,
            self.current_phone,
            self.current_email_hash,
        }
        tokens.update(self.historical_emails)
        tokens.update(self.historical_phones)
        tokens.update(self.historical_email_hashes)
        return tokens

    def matches_email(self, email: str) -> bool:
        """Check if email matches any current or historical email."""
        if not email:
            return False
        return email.strip().lower() in self.all_emails


class IdentityResolver:
    """Loads and resolves user identities across current snapshots and audit logs."""

    def __init__(
        self,
        identities_path: Optional[Path] = None,
        audit_log_path: Optional[Path] = None,
    ) -> None:
        self.identities_path = identities_path or USER_IDENTITIES_PATH
        self.audit_log_path = audit_log_path or USER_AUDIT_LOG_PATH

        self._users_by_id: Dict[str, UserIdentity] = {}
        self._users_by_email: Dict[str, UserIdentity] = {}
        self._users_by_hash: Dict[str, UserIdentity] = {}
        self._users_by_phone: Dict[str, UserIdentity] = {}
        self._is_loaded: bool = False

    def load(self) -> None:
        """Load identities and historical audit logs from CSV files."""
        if self._is_loaded:
            return

        if not self.identities_path.exists():
            raise FileNotFoundError(f"Identities file not found: {self.identities_path}")
        if not self.audit_log_path.exists():
            raise FileNotFoundError(f"Audit log file not found: {self.audit_log_path}")

        # 1. Load current identity snapshots
        identities_df = pd.read_csv(self.identities_path)
        for _, row in identities_df.iterrows():
            user_id = str(row["user_id"]).strip()
            name = str(row["name"]).strip()
            email = str(row["email"]).strip()
            phone = str(row["phone"]).strip()
            email_hash = str(row["email_hash"]).strip().lower()
            updated_at = str(row["updated_at"]).strip()

            user = UserIdentity(
                user_id=user_id,
                name=name,
                current_email=email,
                current_phone=phone,
                current_email_hash=email_hash,
                updated_at=updated_at,
            )
            self._users_by_id[user_id] = user

        # 2. Load and attach historical audit events
        audit_df = pd.read_csv(self.audit_log_path)
        for _, row in audit_df.iterrows():
            audit_id = str(row["audit_id"]).strip()
            user_id = str(row["user_id"]).strip()
            event_time = str(row["event_time"]).strip()
            field_name = str(row["field_name"]).strip()
            old_value = str(row["old_value"]).strip()
            new_value = str(row["new_value"]).strip()

            user = self._users_by_id.get(user_id)
            if not user:
                continue

            event = IdentityAuditEvent(
                audit_id=audit_id,
                user_id=user_id,
                event_time=event_time,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
            user.audit_events.append(event)

            if field_name == "email":
                if old_value and old_value not in user.historical_emails:
                    user.historical_emails.append(old_value)
            elif field_name == "phone":
                if old_value and old_value not in user.historical_phones:
                    user.historical_phones.append(old_value)
            elif field_name == "email_hash":
                if old_value and old_value not in user.historical_email_hashes:
                    user.historical_email_hashes.append(old_value)

        # 3. Build global fast-lookup indexes
        for user in self._users_by_id.values():
            # Current and historical emails
            for email in user.all_emails:
                self._users_by_email[email] = user

            # Current and historical hashes
            for h in user.all_email_hashes:
                self._users_by_hash[h] = user

            # Current and historical phones
            for phone in user.all_phones:
                self._users_by_phone[phone] = user

        self._is_loaded = True

    def resolve_by_email(self, email: Optional[str]) -> Optional[UserIdentity]:
        """Resolve a user by current or historical email address (case-insensitive)."""
        if not self._is_loaded:
            self.load()
        if not email or not isinstance(email, str):
            return None
        normalized = email.strip().lower()
        return self._users_by_email.get(normalized)

    def resolve_by_user_id(self, user_id: Optional[str]) -> Optional[UserIdentity]:
        """Resolve a user by user_id."""
        if not self._is_loaded:
            self.load()
        if not user_id or not isinstance(user_id, str):
            return None
        return self._users_by_id.get(user_id.strip())

    def resolve_by_hash(self, email_hash: Optional[str]) -> Optional[UserIdentity]:
        """Resolve a user by current or historical SHA-256 email hash."""
        if not self._is_loaded:
            self.load()
        if not email_hash or not isinstance(email_hash, str):
            return None
        return self._users_by_hash.get(email_hash.strip().lower())

    def resolve_by_phone(self, phone: Optional[str]) -> Optional[UserIdentity]:
        """Resolve a user by current or historical phone number."""
        if not self._is_loaded:
            self.load()
        if not phone or not isinstance(phone, str):
            return None
        return self._users_by_phone.get(phone.strip())

    def resolve_by_identifier(self, identifier: Optional[str]) -> Optional[UserIdentity]:
        """Attempt resolution by email, user_id, hash, or phone."""
        if not identifier:
            return None
        ident = identifier.strip()
        # Try user_id first if format matches user_...
        if ident.startswith("user_"):
            user = self.resolve_by_user_id(ident)
            if user:
                return user

        # Try email
        user = self.resolve_by_email(ident)
        if user:
            return user

        # Try hash (64 hex characters)
        if len(ident) == 64:
            user = self.resolve_by_hash(ident)
            if user:
                return user

        # Try phone
        user = self.resolve_by_phone(ident)
        if user:
            return user

        return None

    def get_all_users(self) -> List[UserIdentity]:
        """Return list of all loaded user identities."""
        if not self._is_loaded:
            self.load()
        return list(self._users_by_id.values())
