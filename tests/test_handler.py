from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import boto3
from botocore.exceptions import ClientError

from src.handler import lambda_handler


CONFIG = {"bucket": "test-backups", "key": "db/latest.gz", "minSizeBytes": 100, "maxAgeHours": 24}


def test_healthy(monkeypatch):
    client = Mock()
    client.head_object.return_value = {
        "ContentLength": 100,
        "LastModified": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    monkeypatch.setattr(boto3, "client", lambda service: client)
    result = lambda_handler(CONFIG, None)
    assert result == {"status": "HEALTHY", "reason": "ALL_CHECKS_PASSED"}
    client.head_object.assert_called_once_with(Bucket="test-backups", Key="db/latest.gz")


def test_missing(monkeypatch):
    client = Mock()
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not found"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        "HeadObject",
    )
    monkeypatch.setattr(boto3, "client", lambda service: client)
    assert lambda_handler(CONFIG, None)["status"] == "MISSING"


def test_forbidden_is_error(monkeypatch):
    client = Mock()
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
        "HeadObject",
    )
    monkeypatch.setattr(boto3, "client", lambda service: client)
    assert lambda_handler(CONFIG, None)["status"] == "ERROR"


def test_invalid_config():
    assert lambda_handler({"bucket": "hello"}, None)["status"] == "ERROR"
