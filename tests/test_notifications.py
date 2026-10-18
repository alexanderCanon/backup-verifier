import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from notifications import publish_failure


@pytest.mark.parametrize("status", ["MISSING", "UNHEALTHY", "ERROR"])
def test_failed_status_publishes_each_time(status):
    sns = Mock()
    result = {"status": status, "reason": "CHECK_FAILED"}
    for _ in range(2):
        assert publish_failure(sns, "arn:aws:sns:us-east-1:123456789012:alerts",
                               "postgres", result, "2026-10-18T12:00:00+00:00")
    assert sns.publish.call_count == 2
    payload = json.loads(sns.publish.call_args.kwargs["Message"])
    assert payload == {"backupId": "postgres", "status": status,
                       "reason": "CHECK_FAILED", "checkedAt": "2026-10-18T12:00:00+00:00"}


def test_healthy_does_not_publish():
    sns = Mock()
    assert publish_failure(sns, "topic", "postgres",
                           {"status": "HEALTHY", "reason": "ALL_CHECKS_PASSED"},
                           "2026-10-18T12:00:00+00:00") is False
    sns.publish.assert_not_called()


def test_sns_publish_failure_is_not_silenced():
    sns = Mock()
    sns.publish.side_effect = ClientError({"Error": {"Code": "InternalError"}}, "Publish")
    with pytest.raises(ClientError):
        publish_failure(sns, "topic", "postgres",
                        {"status": "MISSING", "reason": "OBJECT_NOT_FOUND"},
                        "2026-10-18T12:00:00+00:00")
