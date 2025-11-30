# PetAvatar: Anthropomorphic Identity Generation 

PetAvatar is an AI-powered service that transforms photos of your pet into disturbingly professional human-like avatars. Upload a photo of your golden retriever, receive back a middle-aged man in a business suit who somehow captures your dog's essence. Your cat becomes a disapproving HR manager. Your hamster? Entry-level accountant energy.

## Constraints

* Runs on AWS
  * Use Bedrock for all models
* Should use strands agents and agentcore
* No UI as part of this project, should have a REST interface
  * Rest interface should be implemented with API Gateway and tc-functors
* Use the latest python (3.13?) that will work with the AWS services
  * Should use uv / pyproject.toml for python and dependency management
* For initial MVP we con't need any sophisticated authentication/authorization. Just use an API key for the REST interface initially.

Use modern techniques. Its ok to be overly complex as long as it doesn't take too long to build/deploy/iteratte. 

## Features:

### Core Capabilities

#### Multi-Modal Pet Analysis

* Upload photos in any format (JPEG, PNG, HEIC, or blurry phone pics taken at 2am)
* AI analyzes breed, expression, posture, and "vibe"
* Detects subtle personality traits: "This cat has CFO energy"
* Works with dogs, cats, hamsters, fish, reptiles, and "whatever that thing is"

#### Personality-to-Profession Mapping

* Proprietary algorithm matches pet traits to human careers
* Considers 47 personality dimensions including:
  * "Would steal your lunch from the fridge" score
  * "Sends passive-aggressive emails" probability
  * "Actually reads the meeting agenda" likelihood
  * "Takes credit for group projects" index

#### 👔 Professional Avatar Generation

* Creates photorealistic human avatars using Amazon Titan Image Generator
* Automatically selects appropriate business attire:
  * Suit & tie for executive pets
  * Business casual for friendly breeds
  * Black turtleneck for "visionary" pets
  * Scrubs for pets with "helper" energy
* Background options can include (come up with more): 
  * Office
  * LinkedIn blue gradient
  * Corner office with city view

#### Bio & Identity Package

* Each avatar comes with:
  * Human Name: AI-generated name that "feels right" (Golden Retriever = "Greg," "Doug," or "Buddy")
  * Job Title: Matched to personality analysis
  * LinkedIn Summary: 3-paragraph professional bio written in corporate speak
  * Skills & Endorsements: Auto-generated from pet behaviors
  * Career Trajectory: Where they started, where they're going
* Similarity Scoring
  * Pet-to-Human match percentage
  * "Separated at Birth?" analysis
  * Side-by-side comparison highlighting uncanny parallels
  * Shareable report card

## Project Structure

```
.
├── topology.yml                 # tc-functors topology definition
├── functions/                   # Lambda function handlers
│   ├── presigned-url-handler/  # Generate S3 upload URLs
│   ├── process-handler/        # Initiate processing
│   ├── s3-event-handler/       # Handle S3 upload events
│   ├── status-handler/         # Check job status
│   ├── result-handler/         # Retrieve results
│   └── process-worker/         # Orchestrate avatar generation
├── src/                        # Shared Python modules
│   ├── agent/                  # Strands Agent code
│   ├── handlers/               # Shared handler utilities
│   └── utils/                  # Common utilities
├── scripts/                    # Infrastructure scripts
│   └── create-infrastructure.py
└── tests/                      # Test suite
```

## API Endpoints

### GET /presigned-url
Generate a presigned S3 URL for uploading pet images.

**Headers**: `x-api-key: <your-api-key>`

**Response**:
```json
{
  "job_id": "uuid",
  "upload_url": "https://s3.amazonaws.com/...",
  "upload_fields": {...},
  "expires_in": 900
}
```

### POST /process
Initiate processing for an uploaded image.

**Headers**: `x-api-key: <your-api-key>`

**Body**:
```json
{
  "s3_uri": "s3://bucket/uploads/job-id/image.jpg"
}
```

**Response**:
```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Processing initiated"
}
```

### GET /status/{job_id}
Check the processing status of a job.

**Headers**: `x-api-key: <your-api-key>`

**Response**:
```json
{
  "job_id": "uuid",
  "status": "queued|processing|completed|failed",
  "progress": 0-100
}
```

### GET /results/{job_id}
Retrieve the completed avatar and identity package.

**Headers**: `x-api-key: <your-api-key>`

**Response**:
```json
{
  "job_id": "uuid",
  "avatar_url": "https://s3.amazonaws.com/...",
  "identity": {
    "human_name": "Greg Thompson",
    "job_title": "Senior Product Manager",
    "seniority": "senior",
    "bio": "...",
    "skills": [...],
    "career_trajectory": {...},
    "similarity_score": 87.5
  },
  "pet_analysis": {...}
}
```

## Deployment

See [TOPOLOGY.md](TOPOLOGY.md) for detailed deployment instructions.

### Quick Start

1. **Create Infrastructure**:
   ```bash
   python scripts/create-infrastructure.py
   ```

2. **Deploy Topology**:
   ```bash
   tc create
   ```

3. **Deploy Strands Agent**:
   ```bash
   cd src/agent
   agentcore launch
   ```

4. **Configure Environment Variables** in Lambda functions

5. **Set up S3 Event Notifications** for automatic processing
