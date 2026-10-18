"""Publish a notification for every failed backup check."""

import json

from verifier import Status


ALERT_STATUSES = {Status.MISSING, Status.UNHEALTHY, Status.ERROR}


def publish_failure(sns, topic_arn, backup_id, result, checked_at):
    if result["status"] not in ALERT_STATUSES:
        return False

    message = {
        "backupId": backup_id,
        "status": str(result["status"]),
        "reason": result["reason"],
        "checkedAt": checked_at,
    }
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"Backup Verifier: {result['status']} - {backup_id}"[:100],
        Message=json.dumps(message),
    )
    return True
