"""Backup metadata validation. No AWS operations are performed in this module."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class Status(StrEnum):
    HEALTHY = "HEALTHY"
    MISSING = "MISSING"
    UNHEALTHY = "UNHEALTHY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Config:
    bucket: str
    key: str
    min_size_bytes: int
    max_age_hours: float

    @classmethod
    def from_event(cls, event):
        if not isinstance(event, dict):
            raise ValueError("Event must be an object")
        try:
            bucket = event["bucket"]
            key = event["key"]
            min_size = event["minSizeBytes"]
            max_age = event["maxAgeHours"]
        except KeyError as exc:
            raise ValueError(f"Missing configuration: {exc.args[0]}") from exc
        if not isinstance(bucket, str) or not bucket.strip():
            raise ValueError("bucket must be a nonempty string")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a nonempty string")
        if type(min_size) is not int or min_size < 0:
            raise ValueError("minSizeBytes must be a nonnegative integer")
        if type(max_age) not in (int, float) or not 0 < max_age < float("inf"):
            raise ValueError("maxAgeHours must be a positive finite number")
        return cls(bucket, key, min_size, float(max_age))


def evaluate(metadata: dict, config: Config, now: datetime | None = None) -> dict:
    """Evaluate S3 HeadObject metadata, returning a stable status and reason."""
    now = now or datetime.now(timezone.utc)
    modified = metadata["LastModified"]
    if modified.tzinfo is None or modified.utcoffset() is None:
        raise ValueError("LastModified must be timezone-aware")
    if metadata["ContentLength"] < config.min_size_bytes:
        return {"status": Status.UNHEALTHY, "reason": "SIZE_BELOW_MINIMUM"}
    if (now - modified).total_seconds() > config.max_age_hours * 3600:
        return {"status": Status.UNHEALTHY, "reason": "BACKUP_TOO_OLD"}
    return {"status": Status.HEALTHY, "reason": "ALL_CHECKS_PASSED"}
