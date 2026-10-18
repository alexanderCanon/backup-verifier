from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from verifier import Config, evaluate


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
CONFIG = Config("backups", "db.gz", 100, 24)


@pytest.mark.parametrize(
    ("size", "age_hours", "status", "reason"),
    [
        (100, 24, "HEALTHY", "ALL_CHECKS_PASSED"),
        (99, 1, "UNHEALTHY", "SIZE_BELOW_MINIMUM"),
        (100, 24.01, "UNHEALTHY", "BACKUP_TOO_OLD"),
        (1000, 1, "HEALTHY", "ALL_CHECKS_PASSED"),
    ],
)
def test_size_and_age(size, age_hours, status, reason):
    metadata = {"ContentLength": size, "LastModified": NOW - timedelta(hours=age_hours)}
    result = evaluate(metadata, CONFIG, NOW)
    assert result == {"status": status, "reason": reason}


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"bucket": "b", "key": "k", "minSizeBytes": -1, "maxAgeHours": 24},
        {"bucket": "b", "key": "k", "minSizeBytes": 1, "maxAgeHours": 0},
        {"bucket": "b", "key": "k", "minSizeBytes": True, "maxAgeHours": 24},
        {"bucket": "", "key": "k", "minSizeBytes": 1, "maxAgeHours": 24},
    ],
)
def test_invalid_config(event):
    with pytest.raises(ValueError):
        Config.from_event(event)


def test_naive_s3_timestamp_is_rejected():
    with pytest.raises(ValueError):
        evaluate({"ContentLength": 100, "LastModified": datetime(2026, 10, 18)}, CONFIG, NOW)


def test_dynamodb_decimal_configuration_is_accepted():
    config = Config.from_event({
        "bucket": "backups",
        "key": "db.gz",
        "minSizeBytes": Decimal("1048576"),
        "maxAgeHours": Decimal("24"),
    })
    assert config.min_size_bytes == 1048576
    assert config.max_age_hours == 24.0
    metadata = {
        "ContentLength": 2097152,
        "LastModified": NOW - timedelta(hours=1),
    }
    assert evaluate(metadata, config, NOW)["status"] == "HEALTHY"


@pytest.mark.parametrize("bad_size", [Decimal("1.5"), Decimal("NaN"), Decimal("-1")])
def test_invalid_dynamodb_decimal_size_is_rejected(bad_size):
    with pytest.raises(ValueError):
        Config.from_event({
            "bucket": "backups",
            "key": "db.gz",
            "minSizeBytes": bad_size,
            "maxAgeHours": Decimal("24"),
        })
