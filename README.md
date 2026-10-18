# AWS Backup Verifier

A small, serverless AWS application to monitor whether database backup objects in Amazon S3 meet basic health rules.

## MVP scope

The first version will verify:

- **Existence** — the expected S3 object exists.
- **Minimum size** — the object meets a configurable size threshold.
- **Maximum age** — the object's last modification time is recent enough.

Planned workflow: EventBridge Scheduler invokes AWS Lambda, which reads backup configuration from DynamoDB, inspects S3 object metadata with `HeadObject`, stores a verification result, and publishes failures to Amazon SNS.

## Stack

- Python 3.13 (Lambda)
- AWS SAM / CloudFormation for infrastructure as code
- Amazon S3, DynamoDB, EventBridge Scheduler, SNS (planned integration)
- pytest for local tests

## Project status

**Scaffold only.** The initial `template.yaml` provisions just a Lambda function. Its handler explicitly returns `NOT_IMPLEMENTED`; it does **not** check backups. No scheduled invocation, S3 permissions, DynamoDB table, or SNS topic have been configured yet.

## Repository layout

```text
.
├── template.yaml
├── src/
│   ├── __init__.py
│   └── handler.py
├── tests/
│   └── test_handler.py
└── README.md
```

## Local development

Requirements: Python 3.13, AWS SAM CLI, and pytest.

```bash
python -m pytest
sam validate
sam build
sam local invoke BackupVerifierFunction --event events/example.json
```

The local invocation step requires creating an event file first; for a quick invocation use `echo '{}' > event.json` followed by `sam local invoke BackupVerifierFunction --event event.json`.

**Do not deploy expecting backup verification yet.** Deployment creates a Lambda scaffold only.

## License

MIT.
