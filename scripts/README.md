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

1. Deploy the tc-functors topology: `tc create`
2. Deploy the Strands Agent: `agentcore launch`
3. Configure Lambda environment variables with resource names/ARNs
4. Set up S3 event notifications to trigger `s3-event-handler`
