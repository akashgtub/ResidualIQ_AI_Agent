"""Temporal filtering module for Ghost Data Still Exists.

Enforces the strict rule from problem statement §6.2:
'Use only information available at or before audit_at when deciding the case.
Evidence created later must not change the answer for that case.'

Handles timezones, timestamp parsing, missing values, and keeps event time
distinct from evidence capture time.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from dateutil import parser as date_parser


def parse_iso_timestamp(ts: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """Conservatively parse an ISO-8601 timestamp string into a UTC timezone-aware datetime.

    Returns None for empty, None, or malformed strings.
    Never silently guesses or defaults unknown timestamps.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    if not isinstance(ts, str):
        return None

    cleaned = ts.strip()
    if not cleaned:
        return None

    try:
        # Standard fast parse for common ISO-8601 UTC format: 2026-09-15T11:59:39Z
        if cleaned.endswith("Z"):
            dt = datetime.fromisoformat(cleaned[:-1])
            return dt.replace(tzinfo=timezone.utc)

        # General dateutil parse for offsets like +00:00, +05:30, etc.
        dt = date_parser.isoparse(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        pass

    try:
        # Fallback dateutil parse for space-delimited formats
        dt = date_parser.parse(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        return None


def is_at_or_before(
    timestamp: Optional[Union[str, datetime]],
    cutoff: Union[str, datetime],
    allow_missing: bool = False,
) -> bool:
    """Return True if timestamp is chronologically at or before cutoff.

    Conservative rule: If timestamp is missing or malformed and allow_missing is False,
    returns False. Unknown timestamps cannot be used as proof that evidence existed
    before the cutoff.
    """
    cutoff_dt = parse_iso_timestamp(cutoff)
    if cutoff_dt is None:
        raise ValueError(f"Invalid audit cutoff timestamp: {cutoff}")

    target_dt = parse_iso_timestamp(timestamp)
    if target_dt is None:
        return allow_missing

    return target_dt <= cutoff_dt


class TemporalFilter:
    """Filters evidence records against a specific case's audit_at cutoff."""

    def __init__(self, audit_at: Union[str, datetime]) -> None:
        self.raw_cutoff = audit_at
        self.cutoff_dt = parse_iso_timestamp(audit_at)
        if self.cutoff_dt is None:
            raise ValueError(f"Invalid audit_at timestamp: {audit_at}")

    def is_eligible(
        self,
        event_time: Optional[Union[str, datetime]] = None,
        capture_time: Optional[Union[str, datetime]] = None,
    ) -> bool:
        """Evaluate whether an item is eligible at or before the audit cutoff.

        - If event_time is provided, it must be <= audit_at.
        - If capture_time is provided and event_time is None, capture_time must be <= audit_at.
        - If both are provided, both must be evaluated: the event must have occurred
          at or before audit_at. Note that evidence captured after audit_at cannot
          prove state at audit_at unless the captured artifact itself reflects the
          state at or before audit_at (e.g. an immutable snapshot or historical event).
        """
        # If capture_time is provided, it must be <= cutoff. Evidence captured after
        # audit_at cannot prove state at audit_at (§6.2, §6.6).
        if capture_time is not None:
            capture_dt = parse_iso_timestamp(capture_time)
            if capture_dt is None or capture_dt > self.cutoff_dt:
                return False

        # If event_time is provided, it must be <= cutoff.
        if event_time is not None:
            event_dt = parse_iso_timestamp(event_time)
            if event_dt is None or event_dt > self.cutoff_dt:
                return False

        # If neither exists, conservatively reject
        if event_time is None and capture_time is None:
            return False

        return True

    def filter_records(
        self,
        records: List[Dict[str, Any]],
        time_field: str = "event_time",
    ) -> List[Dict[str, Any]]:
        """Filter a list of dict records by a timestamp field <= audit_at."""
        eligible = []
        for rec in records:
            ts = rec.get(time_field)
            if ts and is_at_or_before(ts, self.cutoff_dt):
                eligible.append(rec)
        return eligible
