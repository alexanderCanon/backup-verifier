# AWS Backup Verifier

Serverless monitoring of S3 backup objects using AWS Lambda and AWS SAM / CloudFormation.

## V1 health checks

Given a bucket, object key, minimum size (bytes) and maximum age (hours), the Lambda uses S3 `HeadObject` without downloading the backup. It reports:

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

To run against a real S3 object, edit `events/example.json` and invoke:

```bash
sam local invoke BackupVerifierFunction --event events/example.json
```

Note: a real S3 request **requires valid AWS credentials**, network access, and S3 permissions. `sam local invoke` simulates the Lambda runtime but does not emulate S3. Local unit tests do not require AWS.

## Deployment (not required for local tests)

```bash
sam deploy --guided --parameter-overrides BackupBucketName=your-existing-bucket
```

The SAM template declares a Lambda function and S3 read/list access scoped to the given **existing** bucket. It does not create the backup bucket. The invocation event must use that same bucket. Deployment does not yet add a schedule, DynamoDB or SNS; those are tracked in later issues. Deploying may incur AWS costs.

## Example Lambda event

```json
{
  "bucket": "my-backups",
  "key": "database/latest.sql.gz",
  "minSizeBytes": 1048576,
  "maxAgeHours": 24
}
```

## Roadmap

- #3 S3 metadata validations (this change)
- #4 DynamoDB configuration and verification history
- #5 EventBridge schedule
- #6 SNS alerts
- #7 End-to-end deployment verification and documentation

## License

MIT.
