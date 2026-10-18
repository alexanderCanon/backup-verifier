"""Lambda entry point: load configuration, verify S3, store result."""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from storage import BackupNotFound, get_backup_config, save_result
from verifier import Status, evaluate


def check_s3(s3, config):
    try:
        metadata = s3.head_object(Bucket=config.bucket, Key=config.key)
    except ClientError as exc:
        code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code == 404:
            return {"status": Status.MISSING, "reason": "OBJECT_NOT_FOUND"}
        return {"status": Status.ERROR, "reason": f"S3_REQUEST_FAILED: {code or 'unknown'}"}
    except BotoCoreError:
        return {"status": Status.ERROR, "reason": "S3_CLIENT_ERROR"}

    try:
        return evaluate(metadata, config)
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": Status.ERROR, "reason": "INVALID_S3_METADATA"}


def lambda_handler(event, context):
    if not isinstance(event, dict) or not isinstance(event.get("backupId"), str) or not event["backupId"].strip():
        return {"status": Status.ERROR, "reason": "INVALID_BACKUP_ID"}

    backup_id = event["backupId"]
    table = boto3.resource("dynamodb").Table(os.environ["BACKUP_TABLE_NAME"])
    try:
        config = get_backup_config(table, backup_id)
    except BackupNotFound:
        return {"status": Status.ERROR, "reason": "BACKUP_CONFIG_NOT_FOUND"}
    except ValueError:
        return {"status": Status.ERROR, "reason": "INVALID_BACKUP_CONFIG"}
    except (ClientError, BotoCoreError):
        return {"status": Status.ERROR, "reason": "CONFIG_READ_FAILED"}

    result = check_s3(boto3.client("s3"), config)
    # Persistence failures must surface to Lambda; never report a successful
    # check that was not recorded.
    save_result(table, backup_id, result)
    return result
