# Infrastructure Scripts

This directory contains scripts for provisioning and managing AWS infrastructure that is not yet supported by tc-functors.

## Scripts

### create-infrastructure.py

Creates the following AWS resources:

1. **DynamoDB Table** (`petavatar-jobs`)
   - Partition key: `job_id` (String)
   - Billing mode: Pay-per-request
   - Encryption: AWS managed keys
   - TTL enabled on `ttl` attribute for automatic cleanup

2. **S3 Buckets**
   - `petavatar-uploads-{account-id}`: For uploaded pet images
   - `petavatar-generated-{account-id}`: For generated avatars
   - Both configured with:
     - Encryption at rest (AES-256)
     - Public access blocked
     - 7-day lifecycle policy
     - Versioning enabled

3. **API Key** (Secrets Manager)
   - Secret name: `petavatar-api-key`
   - Generates secure random key
   - Used for API authentication

**Usage**:
```bash
python scripts/create-infrastructure.py
```

**Requirements**:
- AWS credentials configured (via `aws configure` or environment variables)
- Permissions to create DynamoDB tables, S3 buckets, and Secrets Manager secrets

### destroy-infrastructure.py

Destroys all infrastructure created by `create-infrastructure.py`.

**Usage**:
```bash
python scripts/destroy-infrastructure.py
```

**Warning**: This will permanently delete all data in the S3 buckets and DynamoDB table. Use with caution!

### configure-lambda-env.py

Generates environment variable values needed for Lambda functions in the tc-functors topology.

**What it does**:
- Verifies that required AWS resources exist
- Generates environment variable values based on your AWS account
- Creates a `.env.petavatar` file with all required values
- Provides deployment instructions

**Environment Variables Generated**:
| Variable | Description | Example Value |
|----------|-------------|---------------|
| `DYNAMODB_TABLE_NAME` | DynamoDB table for job tracking | `petavatar-jobs` |
| `S3_UPLOAD_BUCKET` | S3 bucket for pet image uploads | `petavatar-uploads-123456789012` |
| `S3_GENERATED_BUCKET` | S3 bucket for generated avatars | `petavatar-generated-123456789012` |
| `API_KEY_SECRET_ARN` | Secrets Manager ARN for API key | `arn:aws:secretsmanager:...` |
| `AGENT_RUNTIME_ARN` | Bedrock AgentCore runtime ARN | `arn:aws:bedrock-agentcore:...` |

**Usage**:
```bash
# Generate environment configuration
python scripts/configure-lambda-env.py

# Export variables for tc deployment
source .env.petavatar

# Or export individually
export DYNAMODB_TABLE_NAME="petavatar-jobs"
export S3_UPLOAD_BUCKET="petavatar-uploads-{account-id}"
# ... etc
```

**Note**: After deploying the Strands Agent with `agentcore launch`, update the `AGENT_RUNTIME_ARN` value in `.env.petavatar` with the actual agent ARN.

## Environment Variables

The scripts use the default AWS credentials and region from your environment. You can override these with:

```bash
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
```

## Security Configurations

All resources are created with security best practices:

- **Encryption**: All data encrypted at rest
- **Access Control**: S3 buckets block all public access
- **Lifecycle**: Automatic cleanup after 7 days
- **Tagging**: Resources tagged for tracking and cost allocation

## Next Steps

After running `create-infrastructure.py`:

1. Generate environment configuration: `python scripts/configure-lambda-env.py`
2. Deploy the Strands Agent: `agentcore launch`
3. Update `AGENT_RUNTIME_ARN` in `.env.petavatar` with the actual agent ARN
4. Export environment variables: `source .env.petavatar`
5. Deploy the tc-functors topology: `tc create`
6. Set up S3 event notifications to trigger `s3-event-handler`
