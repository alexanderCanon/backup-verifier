"""AWS Lambda entry point for S3 backup health checks."""

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from verifier import Config, Status, evaluate


def lambda_handler(event, context):
    try:
        config = Config.from_event(event)
    except ValueError as exc:
        return {"status": Status.ERROR, "reason": f"INVALID_CONFIG: {exc}"}

    s3 = boto3.client("s3")
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
