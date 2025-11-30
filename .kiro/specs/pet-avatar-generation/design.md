# Design Document

## Overview

PetAvatar is a serverless AI service that transforms pet photos into professional human avatars with complete career identities. The system uses a multi-stage pipeline orchestrated by Strands Agents, deployed on AWS using tc-functors for infrastructure and AgentCore for agent runtime. The architecture leverages Amazon Bedrock for both image analysis (Claude 3.5 Sonnet for vision) and generation (Titan Image Generator), with asynchronous processing to handle long-running AI operations.

The service exposes a REST API through AWS API Gateway with two upload patterns to handle large image files:
1. **Presigned URL Pattern**: Clients request a presigned S3 URL, upload directly to S3, then request processing
2. **S3 Event Pattern**: External services upload to S3, triggering automatic processing via S3 event notifications

Both patterns avoid API Gateway's 10MB payload limit by using direct S3 uploads. Clients can check processing status and retrieve complete identity packages including photorealistic avatars, generated names, job titles, professional bios, and similarity scores.

## Architecture

### High-Level Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          API Gateway                                  │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │GET /presigned-url│  │POST /process │  │ GET /status  │          │
│  └──────────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐                                                    │
│  │ GET /results │                                                    │
│  └──────────────┘                                                    │
└───────┬──────────────────┬──────────────────┬──────────────┬────────┘
        │                  │                  │              │
        ▼                  ▼                  ▼              ▼
┌──────────────┐    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│presigned-url │    │process-      │  │status-handler│  │result-handler│
│handler       │    │handler       │  │  (Lambda)    │  │  (Lambda)    │
│  (Lambda)    │    │  (Lambda)    │  └──────┬───────┘  └──────┬───────┘
└──────┬───────┘    └──────┬───────┘         │                 │
       │                   │                 ▼                 ▼
       │                   │          ┌─────────────────────────────┐
       │                   │          │      DynamoDB Table         │
       │                   │          │   (Job Status & Results)    │
       │                   │          └─────────────────────────────┘
       │                   │
       │                   ▼
       │            ┌──────────────────────────────────────────┐
       │            │       Processing Queue (SQS)             │
       │            └───────────────┬──────────────────────────┘
       │                            │
       ▼                            ▼
┌─────────────────┐         ┌──────────────┐
│   S3 Buckets    │◄────────│process-worker│
│ - Uploads       │         │  (Lambda)    │
│ - Generated     │         └──────┬───────┘
└────────┬────────┘                │
         │                          ▼
         │                 ┌─────────────────┐
         │                 │ Strands Agent   │
         │                 │ (AgentCore)     │
         │                 └────────┬────────┘
         │                          │
         │       ┌──────────────────┼──────────────────┐
         │       │                  │                  │
         │       ▼                  ▼                  ▼
         │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │  │Pet Analysis  │  │Personality   │  │Avatar        │
         │  │Tool (Bedrock)│  │Mapper Tool   │  │Generator     │
         │  │Claude Vision │  │Claude Text   │  │(Titan Image) │
         │  └──────────────┘  └──────────────┘  └──────┬───────┘
         │                                              │
         └──────────────────────────────────────────────┘
         
         ┌─────────────────┐
         │  S3 Event       │
         │  Notification   │
         └────────┬────────┘
                  │
                  ▼
         ┌──────────────────┐
         │s3-event-handler  │
         │  (Lambda)        │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────────────────────────────┐
         │       Processing Queue (SQS)             │
         └──────────────────────────────────────────┘
```

### Component Interaction Flow

**Pattern 1: Presigned URL Upload**
1. **Request Phase**: Client → GET /presigned-url → presigned-url-handler generates S3 presigned POST URL → returns URL + job ID
2. **Upload Phase**: Client uploads directly to S3 using presigned URL
3. **Process Phase**: Client → POST /process with S3 URI → process-handler validates S3 object → sends to SQS queue
4. **Execution Phase**: process-worker polls SQS → invokes Strands Agent → Agent orchestrates tools → stores results
5. **Retrieval Phase**: Client polls GET /status → Client → GET /results → result-handler returns presigned URLs

**Pattern 2: S3 Event Triggered**
1. **Upload Phase**: External service uploads image to S3 bucket (uploads/{job_id}/*)
2. **Trigger Phase**: S3 event notification → s3-event-handler validates object key → creates DynamoDB record → sends to SQS
3. **Execution Phase**: process-worker polls SQS → invokes Strands Agent → Agent orchestrates tools → stores results
4. **Retrieval Phase**: External service polls GET /status → GET /results → result-handler returns presigned URLs

### Technology Stack

- **Infrastructure**: tc-functors (topology definition), AWS CDK (generated)
- **API Layer**: AWS API Gateway (REST API), Lambda (Python 3.13)
- **Agent Runtime**: Strands Agents SDK, AWS Bedrock AgentCore
- **AI Models**: 
  - Claude 3.5 Sonnet (vision analysis, text generation)
  - Titan Image Generator G1 (avatar generation)
- **Storage**: S3 (images), DynamoDB (job state)
- **Messaging**: SQS (async processing queue)
- **Dependency Management**: uv, pyproject.toml

## Components and Interfaces

### API Handlers (Lambda Functions)

#### presigned-url-handler
**Purpose**: Generate presigned S3 URLs for direct image uploads

**Input**:
```python
# HTTP GET /presigned-url
# Headers: x-api-key: <api_key>
```

**Output**:
```python
{
    "job_id": "uuid-v4",
    "upload_url": "https://s3.amazonaws.com/...",
    "upload_fields": {
        "key": "uploads/{job_id}/image",
        "AWSAccessKeyId": "...",
        "policy": "...",
        "signature": "..."
    },
    "expires_in": 900  # 15 minutes
}
```

**Responsibilities**:
- Validate API key
- Generate unique job ID
- Create S3 presigned POST URL with 15-minute expiration
- Enforce format restrictions (JPEG, PNG, HEIC) in presigned policy
- Enforce 50MB size limit in presigned policy
- Return presigned URL and job ID to client

#### process-handler
**Purpose**: Initiate processing for an uploaded image by S3 URI

**Input**:
```python
# HTTP POST /process
# Headers: x-api-key: <api_key>
# Body: {
#   "s3_uri": "s3://bucket-name/uploads/job-id/image.jpg"
# }
```

**Output**:
```python
{
    "job_id": "uuid-v4",
    "status": "queued",
    "message": "Processing initiated"
}
```

**Responsibilities**:
- Validate API key
- Parse and validate S3 URI format
- Verify S3 object exists and is accessible
- Validate image format (JPEG, PNG, HEIC) and size (<50MB) by checking S3 metadata
- Extract or generate job ID from S3 key
- Create DynamoDB record with status "queued"
- Send message to processing queue
- Return job ID to client

#### s3-event-handler
**Purpose**: Handle S3 upload events and initiate processing automatically

**Input**: S3 event notification (JSON)
```python
{
    "Records": [{
        "s3": {
            "bucket": {"name": "petavatar-uploads-{account}"},
            "object": {"key": "uploads/{job_id}/image.jpg"}
        }
    }]
}
```

**Responsibilities**:
- Parse S3 event notification
- Validate object key matches pattern: uploads/{job_id}/*
- Extract job ID from object key
- Check if DynamoDB record exists, create if not
- Send message to processing queue
- Log invalid events without failing

#### status-handler
**Purpose**: Check processing status for a job

**Input**:
```python
# HTTP GET /status/{job_id}
# Headers: x-api-key: <api_key>
```

**Output**:
```python
{
    "job_id": "uuid-v4",
    "status": "queued" | "processing" | "completed" | "failed",
    "progress": 0-100,  # Optional
    "error": "error message"  # Only if failed
}
```

**Responsibilities**:
- Validate API key
- Query DynamoDB for job status
- Return current status and progress

#### result-handler
**Purpose**: Retrieve completed identity package

**Input**:
```python
# HTTP GET /results/{job_id}
# Headers: x-api-key: <api_key>
```

**Output**:
```python
{
    "job_id": "uuid-v4",
    "avatar_url": "presigned-s3-url",  # 1 hour expiration
    "identity": {
        "human_name": "Greg Thompson",
        "job_title": "Senior Product Manager",
        "seniority": "senior",
        "bio": "Three paragraph LinkedIn bio...",
        "skills": ["Leadership", "Strategic Planning", ...],
        "career_trajectory": {
            "past": "Started as...",
            "present": "Currently leading...",
            "future": "Aspiring to..."
        },
        "similarity_score": 87.5
    },
    "pet_analysis": {
        "species": "dog",
        "breed": "Golden Retriever",
        "personality_traits": {...}
    }
}
```

**Responsibilities**:
- Validate API key
- Check job status is "completed"
- Generate presigned URL for avatar image (1 hour expiration)
- Return complete identity package

#### process-worker
**Purpose**: Orchestrate the avatar generation pipeline

**Input**: SQS message containing job_id and S3 image key

**Responsibilities**:
- Update DynamoDB status to "processing"
- Download image from S3
- Invoke Strands Agent with image and job context
- Handle agent execution (streaming updates optional)
- Store generated avatar to S3
- Update DynamoDB with results or error
- Update status to "completed" or "failed"

### Strands Agent

#### PetAvatarAgent
**Purpose**: Orchestrate the multi-step avatar generation workflow

**Tools**:
1. `analyze_pet_image` - Analyzes pet photo using Claude Vision
2. `map_personality_to_career` - Maps traits to profession using Claude
3. `generate_avatar_image` - Creates human avatar using Titan
4. `generate_identity_package` - Creates bio and career narrative using Claude

**Agent Configuration**:
```python
from strands import Agent, Tool
from strands.models.bedrock import BedrockModel

agent = Agent(
    model=BedrockModel(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"),
    tools=[
        analyze_pet_image_tool,
        map_personality_to_career_tool,
        generate_avatar_image_tool,
        generate_identity_package_tool
    ],
    system_prompt="""You are an AI assistant that transforms pet photos into 
    professional human avatars. Follow this workflow:
    1. Analyze the pet image to extract personality traits
    2. Map those traits to an appropriate human profession
    3. Generate a photorealistic human avatar
    4. Create a complete professional identity package
    
    Be creative but believable. The goal is to capture the pet's essence 
    in human form."""
)
```

**Workflow**:
```
User Input: {image_data, job_id}
    ↓
[analyze_pet_image] → personality_profile
    ↓
[map_personality_to_career] → career_profile
    ↓
[generate_avatar_image] → avatar_image_data
    ↓
[generate_identity_package] → identity_package
    ↓
Return: {avatar_image_data, identity_package, pet_analysis}
```

### Agent Tools

#### analyze_pet_image
**Purpose**: Extract species, breed, expression, and personality traits from pet photo

**Implementation**:
```python
@tool
def analyze_pet_image(image_base64: str) -> dict:
    """
    Analyzes a pet image to extract personality traits and characteristics.
    
    Args:
        image_base64: Base64 encoded pet image
        
    Returns:
        {
            "species": str,
            "breed": str,
            "expression": str,
            "posture": str,
            "personality_dimensions": {
                "confidence": 0-100,
                "energy_level": 0-100,
                "sociability": 0-100,
                "assertiveness": 0-100,
                "playfulness": 0-100,
                # ... 42 more dimensions
            },
            "dominant_traits": [str, str, str],
            "vibe": str  # e.g., "CFO energy", "friendly helper"
        }
    """
```

**Bedrock API Call**:
```python
import boto3
import json

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.invoke_model(
    modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": """Analyze this pet image and provide detailed personality assessment..."""
                }
            ]
        }]
    })
)
```

#### map_personality_to_career
**Purpose**: Map 47 personality dimensions to appropriate human profession

**Implementation**:
```python
@tool
def map_personality_to_career(personality_profile: dict) -> dict:
    """
    Maps pet personality traits to human career profile.
    
    Args:
        personality_profile: Output from analyze_pet_image
        
    Returns:
        {
            "job_title": str,
            "seniority": "entry-level" | "mid-level" | "senior" | "executive",
            "industry": str,
            "work_style": str,
            "attire_style": "suit" | "business_casual" | "creative" | "scrubs",
            "background_setting": "corner_office" | "open_office" | "linkedin_blue" | "creative_space",
            "confidence_score": 0-100
        }
    """
```

**Logic**: Uses Claude to analyze personality dimensions and select profession based on trait patterns. Includes proprietary scoring for traits like "would steal lunch" and "sends passive-aggressive emails".

#### generate_avatar_image
**Purpose**: Create photorealistic human avatar using Titan Image Generator

**Implementation**:
```python
@tool
def generate_avatar_image(career_profile: dict, personality_profile: dict) -> dict:
    """
    Generates a photorealistic human avatar image.
    
    Args:
        career_profile: Output from map_personality_to_career
        personality_profile: Output from analyze_pet_image
        
    Returns:
        {
            "image_base64": str,  # PNG format, 1024x1024
            "prompt_used": str,
            "generation_params": dict
        }
    """
```

**Bedrock API Call**:
```python
response = bedrock.invoke_model(
    modelId='amazon.titan-image-generator-v1',
    body=json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": f"Professional headshot of a {career_profile['seniority']} "
                   f"{career_profile['job_title']}, wearing {career_profile['attire_style']}, "
                   f"{career_profile['background_setting']} background, photorealistic, "
                   f"high quality, professional photography"
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "quality": "premium",
            "cfgScale": 8.0,
            "height": 1024,
            "width": 1024,
            "seed": hash(job_id) % (2**31)  # Deterministic but unique per job
        }
    })
)
```

**Retry Logic**: Implements exponential backoff with 3 retries on failure.

#### generate_identity_package
**Purpose**: Create complete professional identity including name, bio, skills, and career trajectory

**Implementation**:
```python
@tool
def generate_identity_package(
    personality_profile: dict,
    career_profile: dict,
    species: str
) -> dict:
    """
    Generates complete professional identity package.
    
    Args:
        personality_profile: Pet personality analysis
        career_profile: Mapped career information
        species: Pet species (for name generation)
        
    Returns:
        {
            "human_name": str,
            "bio": str,  # 3 paragraphs, LinkedIn style
            "skills": [str],  # 5-10 skills
            "career_trajectory": {
                "past": str,
                "present": str,
                "future": str
            },
            "similarity_score": float  # 0-100
        }
    """
```

**Name Generation Logic**: Uses species-appropriate name patterns (e.g., Golden Retrievers → "Greg", "Doug", "Buddy"; Cats → sophisticated names like "Margaret", "Sebastian").

**Similarity Score Calculation**: Weighted combination of:
- Personality trait alignment (40%)
- Career fit confidence (30%)
- Name appropriateness (15%)
- Overall coherence (15%)

## Data Models

### DynamoDB Schema

**Table Name**: `petavatar-jobs`

**Primary Key**: 
- Partition Key: `job_id` (String, UUID v4)

**Attributes**:
```python
{
    "job_id": "uuid-v4",
    "status": "queued" | "processing" | "completed" | "failed",
    "created_at": "ISO-8601 timestamp",
    "updated_at": "ISO-8601 timestamp",
    "s3_upload_key": "uploads/{job_id}/original.jpg",
    "s3_avatar_key": "generated/{job_id}/avatar.png",  # Only when completed
    "progress": 0-100,  # Optional, for status updates
    "error_message": "string",  # Only when failed
    "identity_package": {  # Only when completed
        "human_name": "string",
        "job_title": "string",
        "seniority": "string",
        "bio": "string",
        "skills": ["string"],
        "career_trajectory": {
            "past": "string",
            "present": "string",
            "future": "string"
        },
        "similarity_score": 87.5
    },
    "pet_analysis": {  # Only when completed
        "species": "string",
        "breed": "string",
        "personality_traits": {}
    },
    "ttl": 1234567890  # 7 days from creation
}
```

**Indexes**: None required (single-item lookups by job_id)

**TTL**: Enabled on `ttl` attribute for automatic cleanup after 7 days

### S3 Bucket Structure

**Bucket 1**: `petavatar-uploads-{account-id}`
- **Purpose**: Store uploaded pet images
- **Lifecycle**: 7-day expiration
- **Encryption**: AES-256 (SSE-S3)
- **Public Access**: Blocked
- **Structure**:
  ```
  uploads/
    {job_id}/
      original.{ext}  # JPEG, PNG, or HEIC
  ```

**Bucket 2**: `petavatar-generated-{account-id}`
- **Purpose**: Store generated avatar images
- **Lifecycle**: 7-day expiration
- **Encryption**: AES-256 (SSE-S3)
- **Public Access**: Blocked (presigned URLs only)
- **Structure**:
  ```
  generated/
    {job_id}/
      avatar.png  # 1024x1024 PNG
  ```

### SQS Message Format

**Queue Name**: `petavatar-processing-queue`

**Message Body**:
```python
{
    "job_id": "uuid-v4",
    "s3_upload_key": "uploads/{job_id}/original.jpg",
    "timestamp": "ISO-8601"
}
```

**Queue Configuration**:
- Visibility Timeout: 900 seconds (15 minutes)
- Message Retention: 4 days
- Dead Letter Queue: `petavatar-processing-dlq` (after 3 retries)

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

Before defining properties, I've identified several areas where properties can be consolidated or where one property implies another:

**Consolidation Opportunities:**
- Properties 1.1, 1.2, and 1.3 all relate to presigned URL generation and can be combined
- Properties 2.3, 2.4, and 2.5 all test S3 event handling and can be combined
- Properties 3.1, 3.2, and 3.3 all relate to S3 URI validation and can be combined
- Properties 4.3, 4.4, and 4.5 all test output structure and can be combined into a schema validation property
- Properties 5.3 and 5.4 both test output structure and can be combined
- Properties 7.2 and 7.3 both test prompt generation and can be combined
- Properties 8.2, 8.3, and 8.4 all test identity package structure and can be combined
- Properties 12.1 and 12.5 both test S3 security configuration and can be combined

**Redundancy Elimination:**
- Property 1.4 (presigned URL returns job ID) is implied by Property 1.1 (presigned URL generation)
- Property 6.5 (results response structure) is implied by testing that results are retrievable (6.4) if we verify the structure when retrieving

After reflection, the following properties provide unique validation value:

### Correctness Properties

Property 1: Presigned URL generation with constraints
*For any* presigned URL request, the system should generate an S3 presigned POST URL with 15-minute expiration that enforces JPEG/PNG/HEIC format restrictions and 50MB size limit in the policy, and return it with a unique job identifier
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

Property 2: Presigned URL expiration enforcement
*For any* presigned URL that has expired, upload attempts should be rejected by S3 with an appropriate error
**Validates: Requirements 1.5**

Property 3: S3 event processing fo

Property 3: Pet analysis produces complete structured output
*For any* valid pet image, the analysis engine should produce a structured profile containing species, expression, posture, and exactly 47 personality dimensions with scores in the range 0-100
**Validates: Requirements 2.1, 2.3, 2.4, 2.5**

Property 4: Personality mapper produces valid career profiles
*For any* personality profile with 47 dimensions, the mapper should output a career profile containing a job title and a seniority level that is one of: "entry-level", "mid-level", "senior", or "executive"
**Validates: Requirements 3.1, 3.3, 3.4**

Property 5: Avatar generator invokes Titan with appropriate prompts
*For any* career profile, the avatar generator should invoke Titan Image Generator with a prompt that includes attire keywords matching the profession and background setting keywords
**Validates: Requirements 4.1, 4.2, 4.3**

Property 6: Avatar generation retry logic
*For any* Titan API failure, the avatar generator should retry up to 3 times with exponential backoff before returning an error
**Validates: Requirements 4.4**

Property 7: Generated avatars meet format requirements
*For any* successfully generated avatar, the image should be in PNG format with dimensions of at least 1024x1024 pixels
**Validates: Requirements 4.5**

Property 8: Identity package structure completeness
*For any* generated identity package, it should contain a human name, a bio with exactly 3 paragraphs, 5-10 skills, a career trajectory with past/present/future fields, and a similarity score between 0-100
**Validates: Requirements 5.2, 5.3, 5.4, 5.5**

Property 9: Upload endpoint returns job ID
*For any* POST request to /upload with a valid API key and valid image, the system should return a unique job identifier and status "queued"
**Validates: Requirements 6.1**

Property 10: Status endpoint returns current state
*For any* GET request to /status/{job_id} with a valid API key, the system should return the current status which is one of: "queued", "processing", "completed", or "failed"
**Validates: Requirements 6.2**

Property 11: Results endpoint returns complete package
*For any* completed job, a GET request to /results/{job_id} should return a JSON response containing avatar_url, human_name, job_title, bio, skills, career_trajectory, similarity_score, and pet_analysis
**Validates: Requirements 6.3, 6.4**

Property 12: Invalid API keys are rejected
*For any* API request with an invalid or missing API key, the system should return a 401 Unauthorized response
**Validates: Requirements 6.5**

Property 13: API Gateway routes to correct handlers
*For any* HTTP request to /upload, /status, or /results, the API Gateway should route it to the corresponding Lambda function (upload-handler, status-handler, or result-handler)
**Validates: Requirements 7.5**

Property 14: Error logging includes context
*For any* error that occurs in any component, the system should log the error with sufficient context including component name, operation, and error details
**Validates: Requirements 9.1**

Property 15: Failed processing returns descriptive errors
*For any* processing failure, the system should update the job status to "failed" and include a descriptive error message in the response
**Validates: Requirements 9.2**

Property 16: Bedrock retry with exponential backoff
*For any* Bedrock API call failure, the system should retry up to 3 times with exponential backoff (delays of 1s, 2s, 4s) before failing
**Validates: Requirements 9.3**

Property 17: Timeout handling
*For any* operation that exceeds the configured timeout limit, the system should terminate gracefully and return a timeout error
**Validates: Requirements 9.4**

Property 18: CloudWatch metrics emission
*For any* system error, the system should emit a CloudWatch metric with error type and component information
**Validates: Requirements 9.5**

Property 19: S3 storage security configuration
*For any* S3 bucket used by the system, it should have encryption at rest enabled and public access blocked
**Validates: Requirements 10.1, 10.5**

Property 20: S3 lifecycle policies
*For any* object stored in S3, it should have a lifecycle policy configured for 7-day expiration
**Validates: Requirements 10.2**

Property 21: Presigned URL expiration
*For any* presigned URL generated for avatar downloads, it should have an expiration time of exactly 1 hour from generation
**Validates: Requirements 10.3**

## Error Handling

### Error Categories

1. **Client Errors (4xx)**
   - Invalid image format → 400 Bad Request
   - Image too large → 413 Payload Too Large
   - Invalid API key → 401 Unauthorized
   - Job not found → 404 Not Found
   - Job not completed → 409 Conflict

2. **Server Errors (5xx)**
   - Bedrock API failures → 503 Service Unavailable (after retries)
   - S3 storage failures → 500 Internal Server Error
   - DynamoDB failures → 500 Internal Server Error
   - Agent execution failures → 500 Internal Server Error
   - Timeout errors → 504 Gateway Timeout

### Retry Strategy

**Bedrock API Calls**:
```python
import time
from typing import Callable, Any

def retry_with_exponential_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> Any:
    """
    Retry a function with exponential backoff.
    
    Delays: 1s, 2s, 4s
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
            # Log retry attempt
```

**SQS Message Processing**:
- Visibility timeout: 15 minutes
- Max receive count: 3
- Dead letter queue for failed messages
- Manual inspection and replay from DLQ

### Error Logging

All errors should be logged with structured context:
```python
import logging
import json

logger = logging.getLogger(__name__)

def log_error(
    component: str,
    operation: str,
    error: Exception,
    context: dict
):
    """Log error with structured context."""
    logger.error(json.dumps({
        "component": component,
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "timestamp": datetime.utcnow().isoformat()
    }))
```

### CloudWatch Metrics

Emit custom metrics for monitoring:
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def emit_metric(metric_name: str, value: float, unit: str = 'Count'):
    """Emit CloudWatch metric."""
    cloudwatch.put_metric_data(
        Namespace='PetAvatar',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        }]
    )

# Example metrics:
# - UploadSuccess / UploadFailure
# - ProcessingSuccess / ProcessingFailure
# - BedrockAPICall / BedrockAPIError
# - AvatarGenerationTime (milliseconds)
# - JobCompletionTime (seconds)
```

## Testing Strategy

### Unit Testing

Unit tests will verify individual components and functions in isolation:

**Test Coverage Areas**:
1. **API Handlers**:
   - Request validation (format, size, API key)
   - Response formatting
   - Error handling
   - DynamoDB interactions
   - S3 presigned URL generation

2. **Agent Tools**:
   - Input validation
   - Bedrock API request formatting
   - Response parsing
   - Error handling
   - Retry logic

3. **Utility Functions**:
   - Image format detection
   - Base64 encoding/decoding
   - Job ID generation
   - Timestamp formatting

**Example Unit Tests**:
```python
def test_validate_image_format_accepts_jpeg():
    """Test that JPEG images are accepted."""
    image_data = create_test_jpeg()
    result = validate_image_format(image_data)
    assert result.is_valid == True
    assert result.format == "jpeg"

def test_validate_image_size_rejects_large_files():
    """Test that files over 10MB are rejected."""
    large_image = create_image_of_size(11 * 1024 * 1024)  # 11MB
    result = validate_image_size(large_image)
    assert result.is_valid == False
    assert "size limit" in result.error_message.lower()

def test_generate_presigned_url_has_one_hour_expiration():
    """Test presigned URLs expire in 1 hour."""
    url = generate_presigned_url("bucket", "key")
    expiration = extract_expiration_from_url(url)
    assert expiration == 3600  # 1 hour in seconds
```

**Testing Framework**: pytest
**Mocking**: unittest.mock for AWS SDK calls
**Coverage Target**: >80% for all modules

### Property-Based Testing

Property-based tests will verify universal properties across many randomly generated inputs:

**Testing Framework**: Hypothesis (Python property-based testing library)

**Configuration**:
```python
from hypothesis import given, settings
import hypothesis.strategies as st

# Run each property test 100 times with different inputs
@settings(max_examples=100)
```

**Property Test Examples**:

```python
from hypothesis import given
import hypothesis.strategies as st

@given(
    image_format=st.sampled_from(['jpeg', 'png', 'heic', 'gif', 'bmp', 'tiff']),
    image_size=st.integers(min_value=0, max_value=20 * 1024 * 1024)
)
def test_property_image_validation(image_format, image_size):
    """
    Property 1: Image format validation
    Feature: pet-avatar-generation, Property 1
    
    For any uploaded file, the system should accept it if and only if 
    it is a valid JPEG, PNG, or HEIC file under 10MB.
    """
    image_data = create_test_image(image_format, image_size)
    result = validate_upload(image_data)
    
    is_valid_format = image_format in ['jpeg', 'png', 'heic']
    is_valid_size = image_size <= 10 * 1024 * 1024
    should_accept = is_valid_format and is_valid_size
    
    assert result.accepted == should_accept
    if not should_accept:
        assert result.error_message is not None

@given(
    personality_dimensions=st.dictionaries(
        keys=st.text(min_size=1),
        values=st.integers(min_value=0, max_value=100),
        min_size=47,
        max_size=47
    )
)
def test_property_career_profile_structure(personality_dimensions):
    """
    Property 4: Personality mapper produces valid career profiles
    Feature: pet-avatar-generation, Property 4
    
    For any personality profile with 47 dimensions, the mapper should 
    output a career profile with valid seniority level.
    """
    profile = {"personality_dimensions": personality_dimensions}
    career = map_personality_to_career(profile)
    
    assert "job_title" in career
    assert "seniority" in career
    assert career["seniority"] in ["entry-level", "mid-level", "senior", "executive"]

@given(
    api_key=st.text(min_size=1, max_size=100),
    endpoint=st.sampled_from(['/upload', '/status/123', '/results/123'])
)
def test_property_invalid_api_key_rejection(api_key, endpoint):
    """
    Property 12: Invalid API keys are rejected
    Feature: pet-avatar-generation, Property 12
    
    For any API request with an invalid API key, the system should 
    return 401 Unauthorized.
    """
    # Assume valid keys are in a known set
    valid_keys = get_valid_api_keys()
    
    response = make_api_request(endpoint, api_key=api_key)
    
    if api_key not in valid_keys:
        assert response.status_code == 401
    else:
        assert response.status_code != 401
```

**Property Test Coverage**:
- All 21 correctness properties will have corresponding property-based tests
- Each test will run 100 iterations with randomly generated inputs
- Tests will be tagged with property numbers for traceability

### Integration Testing

Integration tests will verify component interactions:

1. **End-to-End Upload Flow**:
   - Upload image → verify S3 storage → verify DynamoDB record → verify SQS message

2. **Agent Workflow**:
   - Trigger agent → verify tool calls → verify result storage

3. **API Gateway Integration**:
   - Test routing to Lambda functions
   - Test API key validation
   - Test CORS headers

**Note**: Integration tests will use LocalStack or AWS SAM Local for local testing to avoid AWS costs during development.

### Load Testing

Basic load testing to verify system handles concurrent requests:

**Tool**: Locust or Apache JMeter

**Scenarios**:
1. Concurrent uploads (10-50 simultaneous)
2. Status polling (100 requests/second)
3. Results retrieval (50 requests/second)

**Metrics to Monitor**:
- API Gateway latency
- Lambda cold start times
- SQS queue depth
- DynamoDB throttling
- Bedrock API rate limits

## Deployment Architecture

### tc-functors Topology

The system will be defined using tc-functors topology.yml:

```yaml
name: petavatar

routes:
  /upload:
    method: POST
    function: upload-handler
    cors:
      methods: ['POST', 'OPTIONS']
      origins: ['*']
      allowed_headers: ['Content-Type', 'x-api-key']
  
  /status/{job_id}:
    method: GET
    function: status-handler
    cors:
      methods: ['GET', 'OPTIONS']
      origins: ['*']
      allowed_headers: ['x-api-key']
  
  /results/{job_id}:
    method: GET
    function: result-handler
    cors:
      methods: ['GET', 'OPTIONS']
      origins: ['*']
      allowed_headers: ['x-api-key']

functions:
  upload-handler:
    queue: processing-queue
  
  status-handler:
    # Standalone function
  
  result-handler:
    # Standalone function
  
  process-worker:
    # Triggered by queue

queues:
  processing-queue:
    function: process-worker
    batch_size: 1
    visibility_timeout: 900  # 15 minutes
```

### Strands Agent Deployment

The PetAvatarAgent will be deployed to AWS Bedrock AgentCore:

**Deployment Method**: SDK Integration (Option A)

**Agent Code Structure**:
```
petavatar-agent/
├── agent.py              # Main agent with @app.entrypoint
├── tools/
│   ├── __init__.py
│   ├── analyze_pet.py    # Pet analysis tool
│   ├── map_career.py     # Personality mapper tool
│   ├── generate_avatar.py # Avatar generator tool
│   └── generate_identity.py # Identity package tool
├── requirements.txt
└── pyproject.toml
```

**Deployment Steps**:
1. Install bedrock-agentcore-starter-toolkit
2. Configure agent: `agentcore configure --entrypoint agent.py`
3. Deploy: `agentcore launch`
4. Get agent ARN for Lambda invocation

### Infrastructure Components

**Created by tc-functors**:
- API Gateway REST API
- Lambda functions (upload-handler, status-handler, result-handler, process-worker)
- SQS queue (processing-queue) and DLQ
- IAM roles and policies

**Created manually** (not yet supported by tc-functors):
- DynamoDB table (petavatar-jobs) - created via AWS SDK script
- S3 buckets (uploads, generated) - created via AWS SDK script
- API key for authentication - created via AWS SDK script

**Script**: `scripts/create-infrastructure.py`
```python
import boto3

def create_dynamodb_table():
    dynamodb = boto3.client('dynamodb')
    dynamodb.create_table(
        TableName='petavatar-jobs',
        KeySchema=[{'AttributeName': 'job_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'job_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST',
        TimeToLiveSpecification={'Enabled': True, 'AttributeName': 'ttl'}
    )

def create_s3_buckets():
    s3 = boto3.client('s3')
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    for bucket_name in [f'petavatar-uploads-{account_id}', f'petavatar-generated-{account_id}']:
        s3.create_bucket(Bucket=bucket_name)
        s3.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]
            }
        )
        s3.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            }
        )
        s3.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={
                'Rules': [{
                    'Id': 'DeleteAfter7Days',
                    'Status': 'Enabled',
                    'Expiration': {'Days': 7}
                }]
            }
        )
```

### Environment Variables

Lambda functions will receive environment variables:

```python
DYNAMODB_TABLE_NAME = "petavatar-jobs"
S3_UPLOAD_BUCKET = "petavatar-uploads-{account-id}"
S3_GENERATED_BUCKET = "petavatar-generated-{account-id}"
AGENT_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:{account}:runtime/{agent-id}"
API_KEY_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:{account}:secret:{secret-id}"
AWS_REGION = "us-east-1"
```

## Security Considerations

### Authentication & Authorization

- **API Key**: Stored in AWS Secrets Manager, validated by Lambda authorizer
- **IAM Roles**: Least privilege for Lambda functions
  - upload-handler: S3 PutObject, DynamoDB PutItem, SQS SendMessage
  - status-handler: DynamoDB GetItem
  - result-handler: DynamoDB GetItem, S3 GetObject (for presigned URLs)
  - process-worker: S3 GetObject/PutObject, DynamoDB UpdateItem, Bedrock InvokeModel, AgentCore InvokeAgentRuntime

### Data Protection

- **Encryption at Rest**: S3 (AES-256), DynamoDB (AWS managed keys)
- **Encryption in Transit**: HTTPS for all API calls, TLS for AWS service communication
- **Data Retention**: 7-day automatic deletion via S3 lifecycle and DynamoDB TTL
- **Presigned URLs**: 1-hour expiration to limit exposure

### Network Security

- **S3 Buckets**: Public access blocked, presigned URLs only
- **API Gateway**: CORS configured for specific origins in production
- **Lambda**: VPC not required (all AWS service endpoints support PrivateLink if needed)

### Secrets Management

- **API Keys**: Stored in AWS Secrets Manager, rotated manually
- **AWS Credentials**: IAM roles, no hardcoded credentials
- **Bedrock Access**: IAM role permissions, no API keys

## Monitoring & Observability

### CloudWatch Logs

All Lambda functions and agent executions will log to CloudWatch:

**Log Groups**:
- `/aws/lambda/petavatar-upload-handler`
- `/aws/lambda/petavatar-status-handler`
- `/aws/lambda/petavatar-result-handler`
- `/aws/lambda/petavatar-process-worker`
- `/aws/bedrock-agentcore/petavatar-agent`

**Log Retention**: 7 days (configurable)

### CloudWatch Metrics

**Standard Metrics**:
- Lambda invocations, errors, duration, throttles
- API Gateway requests, latency, 4xx/5xx errors
- SQS messages sent, received, deleted, age
- DynamoDB read/write capacity, throttles

**Custom Metrics**:
- `PetAvatar/UploadSuccess`
- `PetAvatar/UploadFailure`
- `PetAvatar/ProcessingSuccess`
- `PetAvatar/ProcessingFailure`
- `PetAvatar/AvatarGenerationTime`
- `PetAvatar/JobCompletionTime`
- `PetAvatar/BedrockAPICall`
- `PetAvatar/BedrockAPIError`

### CloudWatch Alarms

**Critical Alarms**:
- Lambda error rate > 5%
- API Gateway 5xx error rate > 1%
- SQS queue depth > 100 messages
- DynamoDB throttling events
- Bedrock API error rate > 10%

### Distributed Tracing

**AWS X-Ray**: Enabled for Lambda functions and API Gateway
- Trace upload → queue → processing → agent → tools
- Identify bottlenecks and failures
- Visualize service map

**AgentCore Observability**: 
- Enable CloudWatch Transaction Search
- Add ADOT (AWS Distro for OpenTelemetry) to agent
- View traces, metrics, and logs in CloudWatch GenAI Observability

## Performance Considerations

### Latency Targets

- **Upload API**: < 2 seconds (includes S3 upload)
- **Status API**: < 500ms (DynamoDB query)
- **Results API**: < 1 second (DynamoDB query + presigned URL generation)
- **End-to-End Processing**: < 2 minutes (agent execution with Bedrock calls)

### Scalability

- **API Gateway**: 10,000 requests/second (default limit)
- **Lambda**: 1,000 concurrent executions (default limit, can increase)
- **SQS**: Unlimited throughput
- **DynamoDB**: On-demand capacity, auto-scales
- **Bedrock**: Rate limits vary by model (Claude: 200 RPM, Titan: 100 RPM)

### Cost Optimization

- **Lambda**: Use ARM64 architecture for 20% cost savings
- **S3**: Lifecycle policies for automatic cleanup
- **DynamoDB**: On-demand billing for unpredictable traffic
- **Bedrock**: Cache analysis results when possible (not implemented in MVP)

## Future Enhancements

### Phase 2 Features

1. **Batch Processing**: Upload multiple pets at once
2. **Style Options**: Allow users to select avatar style (corporate, creative, casual)
3. **Background Customization**: Let users choose specific backgrounds
4. **Comparison View**: Side-by-side pet and avatar comparison
5. **Social Sharing**: Generate shareable cards with pet and avatar

### Phase 3 Features

1. **User Accounts**: Authentication with Cognito, save avatar history
2. **Payment Integration**: Stripe for premium features
3. **Advanced Customization**: Fine-tune personality dimensions manually
4. **Video Avatars**: Animated avatars with pet mannerisms
5. **API Rate Limiting**: Per-user quotas and throttling

### Technical Improvements

1. **Caching**: Cache personality analysis for similar pets
2. **CDN**: CloudFront for avatar image delivery
3. **Multi-Region**: Deploy to multiple regions for lower latency
4. **A/B Testing**: Test different prompts and models
5. **Model Fine-Tuning**: Custom Titan model trained on pet-to-human mappings
