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
sam deploy --guided --parameter-overrides BackupBucketName=your-existing-bucket
```

The SAM template declares a Lambda function, a pay-per-request DynamoDB table, and IAM permissions for S3 and DynamoDB. The S3 bucket must already exist; the bucket configured in DynamoDB must match the deployment parameter `BackupBucketName`. Deployment does not add a schedule or SNS yet. Deploying may incur AWS costs.

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

This is an example: replace the bucket, key, and table values with your own. The Lambda looks up `PK=BACKUP#<backupId>`, `SK=CONFIG`, then writes each completed verification as `SK=RUN#<UTC timestamp>#<UUID>` under the same PK. A missing/invalid configuration returns `ERROR` without making an S3 request. A failed DynamoDB write causes the invocation to fail rather than misreporting a successfully recorded check.

For the initial MVP, configuration is entered manually; no management API is needed.

## Example Lambda event

```json
{
  "backupId": "postgres"
}
```

## Roadmap

- #3 S3 metadata validations
- #4 DynamoDB configuration and verification history (this change)
- #5 EventBridge schedule
- #6 SNS alerts
- #7 End-to-end deployment verification and documentation

## License

MIT.
