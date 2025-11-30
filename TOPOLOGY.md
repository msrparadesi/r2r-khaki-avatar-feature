# PetAvatar Topology

This document describes the tc-functors topology for the PetAvatar service.

## Architecture Overview

The PetAvatar service uses a serverless architecture with the following components:

### API Routes

- **GET /presigned-url**: Generate presigned S3 URL for image upload
- **POST /process**: Initiate processing for an uploaded image
- **GET /status/{job_id}**: Check processing status
- **GET /results/{job_id}**: Retrieve completed avatar and identity package

### Lambda Functions

1. **presigned-url-handler**: Generates presigned S3 POST URLs with format/size restrictions
2. **process-handler**: Validates S3 URI and queues processing job
3. **s3-event-handler**: Handles S3 upload events (triggered by S3 notifications)
4. **status-handler**: Returns job status from DynamoDB
5. **result-handler**: Returns completed results with presigned download URLs
6. **process-worker**: Orchestrates avatar generation via Strands Agent

### Message Queue

- **processing-queue**: SQS queue for async avatar generation
  - Batch size: 1 (process one job at a time)
  - Visibility timeout: 900 seconds (15 minutes)
  - Triggers: process-worker Lambda function

## Data Flow

### Pattern 1: Presigned URL Upload
```
Client → GET /presigned-url → presigned-url-handler
Client → Upload to S3 (direct)
Client → POST /process → process-handler → SQS → process-worker
Client → GET /status → status-handler
Client → GET /results → result-handler
```

### Pattern 2: S3 Event Triggered
```
External Service → Upload to S3
S3 Event → s3-event-handler → SQS → process-worker
External Service → GET /status → status-handler
External Service → GET /results → result-handler
```

## Infrastructure Not in Topology

The following resources must be created separately (not yet supported by tc-functors):

1. **DynamoDB Table**: `petavatar-jobs` (created via `scripts/create-infrastructure.py`)
2. **S3 Buckets**: 
   - `petavatar-uploads-{account-id}`
   - `petavatar-generated-{account-id}`
3. **API Key**: Stored in AWS Secrets Manager
4. **S3 Event Notification**: Configure uploads bucket to trigger s3-event-handler

## Environment Variables

Lambda functions require the following environment variables:

- `DYNAMODB_TABLE_NAME`: Name of the jobs table
- `S3_UPLOAD_BUCKET`: Bucket for uploaded images
- `S3_GENERATED_BUCKET`: Bucket for generated avatars
- `AGENT_RUNTIME_ARN`: ARN of the deployed Strands Agent
- `API_KEY_SECRET_ARN`: ARN of the API key in Secrets Manager
- `AWS_REGION`: AWS region (default: us-east-1)

## Deployment

1. Create infrastructure: `python scripts/create-infrastructure.py`
2. Deploy topology: `tc create`
3. Deploy Strands Agent: `agentcore launch`
4. Configure S3 event notifications
5. Set Lambda environment variables

## CORS Configuration

All routes are configured with CORS to allow:
- Origins: `*` (configure specific origins in production)
- Headers: `Content-Type`, `x-api-key`
- Methods: Appropriate for each endpoint

## Security

- API key validation on all endpoints
- S3 buckets with public access blocked
- Presigned URLs with time-limited access
- IAM roles with least privilege
- Encryption at rest for S3 and DynamoDB
