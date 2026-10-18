from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError

from src.handler import lambda_handler


CONFIG = {"bucket": "test-backups", "key": "db/latest.gz", "minSizeBytes": 100, "maxAgeHours": 24}


@pytest.fixture
def aws(monkeypatch):
    table = Mock()
    table.get_item.return_value = {"Item": CONFIG}
    client = Mock()
    client.head_object.return_value = {
        "ContentLength": 100,
        "LastModified": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    resource = Mock()
    resource.Table.return_value = table
    monkeypatch.setenv("BACKUP_TABLE_NAME", "test-table")
    monkeypatch.setattr(boto3, "resource", lambda name: resource)
    monkeypatch.setattr(boto3, "client", lambda name: client)
    return table, client


def test_healthy_result_is_stored(aws):
    table, s3 = aws
    assert lambda_handler({"backupId": "postgres"}, None)["status"] == "HEALTHY"
    table.get_item.assert_called_once_with(
        Key={"PK": "BACKUP#postgres", "SK": "CONFIG"}, ConsistentRead=True
    )
    s3.head_object.assert_called_once_with(Bucket="test-backups", Key="db/latest.gz")
    recorded = table.put_item.call_args.kwargs["Item"]
    assert recorded["PK"] == "BACKUP#postgres"
    assert recorded["SK"].startswith("RUN#")
    assert recorded["status"] == "HEALTHY"
    assert recorded["checkedAt"]


@pytest.mark.parametrize("code,expected", [(404, "MISSING"), (403, "ERROR"), (500, "ERROR")])
def test_s3_failures_are_stored(aws, code, expected):
    table, s3 = aws
    s3.head_object.side_effect = ClientError(
        {"Error": {"Code": str(code)}, "ResponseMetadata": {"HTTPStatusCode": code}},
        "HeadObject",
    )
    assert lambda_handler({"backupId": "postgres"}, None)["status"] == expected
    assert table.put_item.call_args.kwargs["Item"]["status"] == expected


def test_missing_config_is_recorded_without_s3_request(aws):
    table, s3 = aws
    table.get_item.return_value = {}
    assert lambda_handler({"backupId": "unknown"}, None) == {
        "status": "ERROR", "reason": "BACKUP_CONFIG_NOT_FOUND"
    }
    s3.head_object.assert_not_called()
    assert table.put_item.call_args.kwargs["Item"]["reason"] == "BACKUP_CONFIG_NOT_FOUND"


def test_invalid_event(aws):
    table, s3 = aws
    assert lambda_handler({}, None)["status"] == "ERROR"
    table.get_item.assert_not_called()
    s3.head_object.assert_not_called()


def test_invalid_stored_configuration(aws):
    table, s3 = aws
    table.get_item.return_value = {"Item": {"bucket": "test-backups"}}
    assert lambda_handler({"backupId": "postgres"}, None)["reason"] == "INVALID_BACKUP_CONFIG"
    s3.head_object.assert_not_called()
    assert table.put_item.call_args.kwargs["Item"]["reason"] == "INVALID_BACKUP_CONFIG"


def test_failed_persistence_is_not_silenced(aws):
    table, _ = aws
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "PutItem"
    )
    with pytest.raises(ClientError):
        lambda_handler({"backupId": "postgres"}, None)


def test_healthy_sends_no_notification(aws, monkeypatch):
    table, s3 = aws
    sns = Mock()
    original_client = boto3.client
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:alerts")
    monkeypatch.setattr(boto3, "client", lambda service: sns if service == "sns" else original_client(service))
    assert lambda_handler({"backupId": "postgres"}, None)["status"] == "HEALTHY"
    sns.publish.assert_not_called()


def test_missing_sends_alert_after_record(aws, monkeypatch):
    table, s3 = aws
    sns = Mock()
    s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        "HeadObject",
    )
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:alerts")
    monkeypatch.setattr(boto3, "client", lambda service: sns if service == "sns" else s3)
    assert lambda_handler({"backupId": "postgres"}, None)["status"] == "MISSING"
    table.put_item.assert_called_once()
    sns.publish.assert_called_once()
    import json
    message = json.loads(sns.publish.call_args.kwargs["Message"])
    assert message["status"] == "MISSING"
    assert message["checkedAt"] == table.put_item.call_args.kwargs["Item"]["checkedAt"]


def test_config_read_failure_sends_error_alert(aws, monkeypatch):
    table, s3 = aws
    table.get_item.side_effect = ClientError(
        {"Error": {"Code": "InternalServerError"}}, "GetItem"
    )
    sns = Mock()
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:alerts")
    monkeypatch.setattr(boto3, "client", lambda service: sns if service == "sns" else s3)
    assert lambda_handler({"backupId": "postgres"}, None)["reason"] == "CONFIG_READ_FAILED"
    table.put_item.assert_not_called()
    sns.publish.assert_called_once()
