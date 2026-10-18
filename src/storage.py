"""DynamoDB access for backup configuration and verification history."""

from datetime import datetime, timezone
from uuid import uuid4

from verifier import Config


class BackupNotFound(Exception):
    pass


def get_backup_config(table, backup_id):
    response = table.get_item(
        Key={"PK": f"BACKUP#{backup_id}", "SK": "CONFIG"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if item is None:
        raise BackupNotFound(backup_id)
    return Config.from_event(item)


def save_result(table, backup_id, result):
    checked_at = datetime.now(timezone.utc).isoformat()
    item = {
        "PK": f"BACKUP#{backup_id}",
        "SK": f"RUN#{checked_at}#{uuid4()}",
        "checkedAt": checked_at,
        "status": str(result["status"]),
        "reason": result["reason"],
    }
    table.put_item(Item=item)
    return item
