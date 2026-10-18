# AWS Backup Verifier

Serverless monitoring of S3 backup objects using AWS Lambda and AWS SAM / CloudFormation.

## V1 health checks

Given a backup ID, Lambda reads its bucket, object key, minimum size (bytes) and maximum age (hours) from DynamoDB, then uses S3 `HeadObject` without downloading the backup. It reports:

- `HEALTHY`: size and age thresholds pass.
- `MISSING`: S3 returns HTTP 404.
- `UNHEALTHY`: backup is too small or too old.
- `ERROR`: invalid configuration, permissions, service failure or unexpected metadata.

These metadata checks **do not prove a backup can be restored**.

## Development

Python 3.13, AWS SAM CLI, Docker (for `sam local invoke`).

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
sam validate
sam build
```

To run against a real S3 object, first deploy and insert a configuration item in DynamoDB. Then edit `events/example.json` with its `backupId` and invoke:

```bash
sam local invoke BackupVerifierFunction --event events/example.json
```

Note: a real S3 request **requires valid AWS credentials**, network access, and S3 permissions. `sam local invoke` simulates the Lambda runtime but does not emulate S3. Local unit tests do not require AWS.

## Deployment (not required for local tests)

```bash
sam deploy --guided --parameter-overrides BackupBucketName=your-existing-bucket BackupId=postgres VerificationSchedule='rate(1 day)' SchedulerState=DISABLED
```

The SAM template declares a Lambda function, a pay-per-request DynamoDB table, and IAM permissions for S3 and DynamoDB. The S3 bucket must already exist; the bucket configured in DynamoDB must match the deployment parameter `BackupBucketName`. Deployment adds an EventBridge Scheduler schedule (disabled by default) and an SNS topic for failure alerts. Deploying may incur AWS costs.

### Configuration

After deployment, find the table name in stack outputs. Insert one configuration item (manually in DynamoDB console, or using AWS CLI) with these attributes:

```json
{
  "PK": "BACKUP#postgres",
  "SK": "CONFIG",
  "bucket": "my-backups",
  "key": "database/latest.sql.gz",
  "minSizeBytes": 1048576,
  "maxAgeHours": 24
}
```

Use string types for `PK`, `SK`, `bucket`, `key`; use DynamoDB Number for `minSizeBytes` and `maxAgeHours`. For example, with AWS CLI:

```bash
aws dynamodb put-item --table-name YOUR_STACK_TABLE_NAME --item '{
  "PK": {"S": "BACKUP#postgres"},
  "SK": {"S": "CONFIG"},
  "bucket": {"S": "my-backups"},
  "key": {"S": "database/latest.sql.gz"},
  "minSizeBytes": {"N": "1048576"},
  "maxAgeHours": {"N": "24"}
}'
```

This is an example: replace the bucket, key, and table values with your own. The Lambda looks up `PK=BACKUP#<backupId>`, `SK=CONFIG`, then writes each completed verification as `SK=RUN#<UTC timestamp>#<UUID>` under the same PK. A missing/invalid configuration returns `ERROR`, records the result, and skips the S3 request. A failed DynamoDB write causes the invocation to fail rather than misreporting a successfully recorded check.

For the initial MVP, configuration is entered manually; no management API is needed.

### Scheduled verification (issue #5)

AWS SAM's `ScheduleV2` creates an EventBridge Scheduler schedule and the necessary target invocation IAM role. Each scheduled invocation sends this exact JSON to the existing Lambda: `{"backupId":"postgres"}` (where `postgres` is the `BackupId` parameter). The Lambda handler remains manually invokable with the same event.

Parameters:
- `BackupId`: backup configuration ID, default `postgres`.
- `VerificationSchedule`: EventBridge Scheduler expression, default `rate(1 day)`.
- `SchedulerState`: `DISABLED` (default) or `ENABLED`.

**Why disabled by default?** A schedule should not start checking a missing configuration as soon as a new stack is deployed. First insert the DynamoDB `CONFIG` item shown above; then update the stack with `SchedulerState=ENABLED` (preserving the same bucket and other parameters). Future schedule changes require only updating `VerificationSchedule` and redeploying, not changing Python.

Example initial deployment:

```bash
sam deploy --guided --parameter-overrides BackupBucketName=my-backups BackupId=postgres VerificationSchedule='rate(1 day)' SchedulerState=DISABLED
```

After creating the CONFIG item, use the same deployment parameters with `SchedulerState=ENABLED`. Confirm parameter values when using `sam deploy --guided`; review its change set before approving. The schedule is in UTC with flexible windows disabled, but the execution is not a hard real-time guarantee. Each configured stack schedule checks one backup ID. The Scheduler only triggers Lambda: a successful invocation **does not imply** that the backup is healthy. SNS sends an alert for each failed check (issue #6).

### Failure notifications (issue #6)

The stack provisions one Amazon SNS topic, returned as `BackupAlertTopicArn` in CloudFormation stack outputs. Add an email subscription through the SNS console, or using AWS CLI:

```bash
aws sns subscribe --topic-arn YOUR_TOPIC_ARN --protocol email --notification-endpoint you@example.com
```

**Confirm the subscription** using the verification link sent to that mailbox, or email alerts will not be delivered. No email address is hard-coded in the template.

Every check returning `MISSING`, `UNHEALTHY` or `ERROR` publishes an alert with `backupId`, `status`, `reason`, and `checkedAt` in UTC. `HEALTHY` produces no alert. Repeated failures produce repeated messages; there is no state-transition logic or deduplication.

For a valid backup ID, a DynamoDB configuration read failure also publishes an `ERROR` alert, but cannot record the result if DynamoDB is unavailable. Missing/invalid configuration can be recorded and alerted. Malformed events with no valid backup ID return `ERROR` without SNS because an identifier is unavailable. If DynamoDB result persistence or SNS publishing fails, the Lambda invocation fails; retries could generate repeated notifications. Monitoring delivery failures is part of integration testing (#7).

## Example Lambda event

```json
{
  "backupId": "postgres"
}
```

## Roadmap

- #3 S3 metadata validations
- #4 DynamoDB configuration and verification history
- #5 EventBridge schedule
- #6 SNS alerts (this change)
- #7 End-to-end deployment verification and documentation

## License

MIT.
