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

Python 3.13 and AWS SAM CLI. Docker is needed for `sam local invoke` and for `sam build --use-container`, but not for unit tests or builds using a matching local Python runtime. GitHub Actions runs tests, `sam validate --lint` and `sam build` on Python 3.13.

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

### Verify an AWS deployment

Set the AWS region explicitly (the examples use `us-east-1`); replace placeholders with your stack's real outputs:

```bash
aws cloudformation describe-stacks --stack-name YOUR_STACK_NAME --region us-east-1 \
  --query 'Stacks[0].Outputs'
```

Create the DynamoDB `CONFIG` item as shown above and ensure the S3 key exists. Invoke the Lambda and read the payload file:

```bash
aws lambda invoke --region us-east-1 \
  --function-name YOUR_FUNCTION_NAME \
  --cli-binary-format raw-in-base64-out \
  --payload '{"backupId":"postgres"}' response.json
cat response.json
```

Expected healthy payload: `{"status":"HEALTHY","reason":"ALL_CHECKS_PASSED"}`, provided the object meets both thresholds. The CLI invocation's success is **not** equivalent to a successful verification; inspect the returned payload and any `FunctionError`.

Confirm that a run was persisted:

```bash
aws dynamodb query --region us-east-1 --table-name YOUR_STACK_TABLE_NAME \
  --key-condition-expression 'PK = :pk AND begins_with(SK, :run)' \
  --expression-attribute-values '{":pk":{"S":"BACKUP#postgres"},":run":{"S":"RUN#"}}'
```

To exercise SNS delivery without deleting the S3 object, temporarily increase `minSizeBytes` above its actual size, invoke again, and confirm an `UNHEALTHY` / `SIZE_BELOW_MINIMUM` response, a persisted run, and an SNS email. **Restore the original threshold afterward.** The SNS email subscription must have been confirmed beforehand.

To inspect (but not activate) the schedule:

```bash
aws scheduler get-schedule --region us-east-1 \
  --name BackupVerifierFunctionPeriodicVerification \
  --query '{State:State,Expression:ScheduleExpression,Target:Target.Arn}'
```

`list-schedules` does not return `ScheduleExpression`; use `get-schedule` for that field. A configured `DISABLED` schedule is not an end-to-end test of scheduled delivery.

### Observed deployed test (2026-10-18)

In a test stack in `us-east-1`, a synthetic 2 MiB object at `database/latest.sql.gz` was checked against an initial 1 MiB minimum and 24-hour maximum age. The first invocation recorded `ERROR / INVALID_BACKUP_CONFIG`: boto3's DynamoDB resource returns Number attributes as `Decimal`. PR #12 corrected the validation. A later invocation returned `HEALTHY / ALL_CHECKS_PASSED`, and both runs were confirmed in DynamoDB. Raising the minimum to 10 MiB produced `UNHEALTHY / SIZE_BELOW_MINIMUM`, with a confirmed SNS email delivery; the user restored the original minimum afterward.

CloudFormation reported `CREATE_COMPLETE` for the stack. EventBridge Scheduler was inspected and showed `DISABLED` with `rate(1 day)`; **automatic scheduled invocation has not been tested**. Missing-object, expired-object, and AWS access-denied cases have not yet been confirmed against deployed AWS resources. Unit tests cover application behavior but do not establish production integration for those cases.

### Cost, security, and cleanup

AWS Lambda, DynamoDB (on-demand), S3, EventBridge Scheduler, SNS, CloudFormation and SAM's managed deployment bucket have separate billing/quota considerations. The exact bill varies by region, requests, stored bytes and current AWS pricing. This project is not guaranteed to be free; avoid enabling unnecessary recurring checks. IAM restricts the Lambda's S3 access to the bucket configured at deployment. SNS alerts contain backup metadata, not backup contents. The checker uses S3 metadata only: **it cannot prove that the backup is intact or restorable**.

The configured backup S3 bucket is **external to this CloudFormation stack**. Deleting the stack does not delete backup objects or that bucket. Before cleanup, confirm the stack name and region. For a SAM-managed test stack:

```bash
sam delete --stack-name YOUR_STACK_NAME --region us-east-1
```

Review confirmation prompts and any deletion errors. This removes managed Lambda, DynamoDB (including its records), SNS topic and schedule; the SAM-managed artifact bucket may be shared with other deployments, so do **not** delete it indiscriminately. Remove only test objects/buckets that you explicitly own and no longer need. An SNS email subscription may need separate review if its topic has been removed. The DynamoDB history is not retained by this template on stack deletion.

### Troubleshooting

- `ResourceNotFoundException` querying DynamoDB: verify AWS account, `--region` and the table name from CloudFormation outputs.
- `INVALID_BACKUP_CONFIG`: check the required fields and DynamoDB Number types; use a version with the DynamoDB `Decimal` fix (PR #12).
- A healthy-looking `aws lambda invoke` CLI response does not prove `HEALTHY`; check `response.json`.
- No SNS email: confirm the subscription, then check the Lambda outcome and CloudWatch logs.
- Local `sam build` fails due to Python version mismatch: use Python 3.13 locally, a compatible container build, or the existing Python 3.13 GitHub Actions build. Container images can use several GB of disk; Docker is not required for plain tests.

## Roadmap

- #3 S3 metadata validations
- #4 DynamoDB configuration and verification history
- #5 EventBridge schedule
- #6 SNS alerts
- #7 End-to-end deployment verification and documentation

## License

MIT.
