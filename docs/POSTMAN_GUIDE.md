# PetAvatar API - Postman Guide

This guide explains how to use the PetAvatar API with Postman to transform pet photos into professional human avatars.

## API Information

| Property | Value |
|----------|-------|
| **Base URL** | `https://42kw05zl4d.execute-api.us-west-2.amazonaws.com` |
| **API Key** | `nX92rzyA9PVj3lniXfHb6H1Uzk3fC8oOgTNRnUjHMSw` |

> **Note:** Retrieve the current API key from AWS Secrets Manager if it has been rotated.
| **Region** | `us-west-2` |

## Postman Setup

### 1. Create Environment Variables (Recommended)

In Postman, create a new environment with these variables:

| Variable | Value |
|----------|-------|
| `base_url` | `https://42kw05zl4d.execute-api.us-west-2.amazonaws.com` |
| `api_key` | `nX92rzyA9PVj3lniXfHb6H1Uzk3fC8oOgTNRnUjHMSw` |
| `job_id` | *(leave empty - will be set automatically)* |

### 2. Configure Headers

All API requests require the `x-api-key` header:

```
x-api-key: {{api_key}}
```

## API Endpoints

### 1. Get Presigned Upload URL

Request a presigned S3 URL to upload your pet image.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `{{base_url}}/presigned-url` |
| **Headers** | `x-api-key: {{api_key}}` |

**Example Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_url": "https://petavatar-uploads-456773209430.s3.amazonaws.com/",
  "upload_fields": {
    "key": "uploads/550e8400-e29b-41d4-a716-446655440000/image",
    "AWSAccessKeyId": "...",
    "policy": "...",
    "signature": "..."
  },
  "expires_in": 900
}
```

**Post-response Script (to save job_id):**
```javascript
var jsonData = pm.response.json();
pm.environment.set("job_id", jsonData.job_id);
```

---

### 2. Upload Image to S3

Use the presigned URL from step 1 to upload your pet image.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | Use `upload_url` from previous response |
| **Body** | `form-data` |

**Form Data Fields:**
- All fields from `upload_fields` in the previous response
- `file`: Your pet image (JPEG, PNG, or HEIC, max 50MB)

**Important:** The `file` field must be the last field in the form data.

---

### 3. Start Processing

Initiate avatar generation for an uploaded image.

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `{{base_url}}/process` |
| **Headers** | `x-api-key: {{api_key}}`, `Content-Type: application/json` |
| **Body** | JSON |

**Request Body:**
```json
{
  "s3_uri": "s3://petavatar-uploads-456773209430/uploads/{{job_id}}/image"
}
```

**Example Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Processing initiated"
}
```

---

### 4. Check Job Status

Poll this endpoint to check processing progress.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `{{base_url}}/status/{{job_id}}` |
| **Headers** | `x-api-key: {{api_key}}` |

**Example Response (Processing):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 45
}
```

**Example Response (Completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed"
}
```

**Status Values:**
- `queued` - Job is waiting to be processed
- `processing` - Avatar generation in progress
- `completed` - Results are ready
- `failed` - Processing failed (check error message)

---

### 5. Get Results

Retrieve the completed avatar and identity package.

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `{{base_url}}/results/{{job_id}}` |
| **Headers** | `x-api-key: {{api_key}}` |

**Example Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "avatar_url": "https://petavatar-generated-456773209430.s3.amazonaws.com/...",
  "identity": {
    "human_name": "Greg Thompson",
    "job_title": "Senior Product Manager",
    "seniority": "senior",
    "bio": "Greg is a seasoned product leader with over 15 years of experience...",
    "skills": [
      "Strategic Planning",
      "Team Leadership",
      "Product Development",
      "Stakeholder Management",
      "Agile Methodologies"
    ],
    "career_trajectory": {
      "past": "Started as a junior analyst at a tech startup...",
      "present": "Currently leading a team of 12 product managers...",
      "future": "Aspiring to become VP of Product..."
    },
    "similarity_score": 87.5
  },
  "pet_analysis": {
    "species": "dog",
    "breed": "Golden Retriever",
    "personality_traits": {
      "confidence": 85,
      "energy_level": 72,
      "sociability": 95
    }
  }
}
```

---

## Complete Workflow Example

### Step-by-Step Process

1. **Get Presigned URL**
   - Send GET to `/presigned-url`
   - Save the `job_id` and `upload_url`

2. **Upload Pet Image**
   - POST to the `upload_url` with form-data
   - Include all `upload_fields` plus your image file

3. **Start Processing**
   - POST to `/process` with the S3 URI
   - Confirm status is "queued"

4. **Poll Status**
   - GET `/status/{job_id}` every 5-10 seconds
   - Wait until status is "completed"

5. **Get Results**
   - GET `/results/{job_id}`
   - Download avatar from `avatar_url`

---

## Error Responses

### 401 Unauthorized
```json
{
  "error": "Invalid or missing API key"
}
```
**Solution:** Ensure `x-api-key` header is set correctly.

### 400 Bad Request
```json
{
  "error": "Invalid S3 URI format. Expected: s3://bucket-name/key"
}
```
**Solution:** Check the S3 URI format in your request.

### 404 Not Found
```json
{
  "error": "Job not found"
}
```
**Solution:** Verify the job_id is correct.

### 409 Conflict
```json
{
  "error": "Job not completed yet"
}
```
**Solution:** Wait for status to be "completed" before requesting results.

### 413 Payload Too Large
```json
{
  "error": "Image exceeds 50MB size limit"
}
```
**Solution:** Reduce image file size before uploading.

---

## Supported Image Formats

| Format | Extension | Max Size |
|--------|-----------|----------|
| JPEG | `.jpg`, `.jpeg` | 50 MB |
| PNG | `.png` | 50 MB |
| HEIC | `.heic` | 50 MB |

---

## Rate Limits

| Endpoint | Rate Limit | Burst Limit |
|----------|------------|-------------|
| `/presigned-url` | 100/sec | 200 |
| `/process` | 50/sec | 100 |
| `/status/{job_id}` | 200/sec | 400 |
| `/results/{job_id}` | 100/sec | 200 |

---

## Tips

1. **Save job_id automatically:** Use Postman's Tests tab to extract and save the job_id to your environment.

2. **Create a Collection:** Organize all endpoints in a Postman collection for easy reuse.

3. **Use Collection Runner:** For batch testing, use Postman's Collection Runner.

4. **Monitor with Console:** Open Postman Console (View > Show Postman Console) to debug requests.

---

## AWS Resources

| Resource | Name/ARN |
|----------|----------|
| Upload Bucket | `petavatar-uploads-456773209430` |
| Generated Bucket | `petavatar-generated-456773209430` |
| DynamoDB Table | `petavatar-jobs` |
| API Key Secret | `arn:aws:secretsmanager:us-west-2:456773209430:secret:petavatar-api-key-b65ShW` |
