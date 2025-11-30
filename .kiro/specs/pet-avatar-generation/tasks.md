# Implementation Plan

- [x] 1. Set up project structure and dependencies
- [x] 1.1 Initialize Python project with uv and pyproject.toml
  - Create project directory structure
  - Configure pyproject.toml with Python 3.13
  - Add core dependencies: boto3, strands-agents, bedrock-agentcore
  - _Requirements: 10.1, 10.2, 10.5_

- [x] 1.2 Create tc-functors topology definition
  - Define topology.yml with routes, functions, queues
  - Configure API Gateway routes: /presigned-url, /process, /status, /results
  - Configure Lambda functions and SQS queue
  - _Requirements: 9.1, 9.5_

- [x] 1.3 Create infrastructure provisioning scripts
  - Write scripts/create-infrastructure.py for DynamoDB table creation
  - Add S3 bucket creation with encryption and lifecycle policies
  - Add API key creation in Secrets Manager
  - _Requirements: 12.1, 12.2, 12.5_

- [-] 2. Implement API handler Lambda functions
- [x] 2.1 Implement presigned-url-handler
  - Create handler function to generate presigned S3 POST URLs
  - Implement API key validation
  - Generate unique job IDs
  - Enforce format and size restrictions in presigned policy
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1_

- [ ]* 2.2 Write property test for presigned URL generation
  - **Property 1: Presigned URL generation with constraints**
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

- [x] 2.3 Implement process-handler
  - Create handler to validate S3 URI and initiate processing
  - Parse and validate S3 URI format
  - Verify S3 object exists and validate format/size
  - Create DynamoDB record and send SQS message
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.2_

- [ ]* 2.4 Write property test for S3 URI validation
  - **Property 3: S3 URI validation and processing**
  - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 2.5 Implement s3-event-handler
  - Create handler for S3 event notifications
  - Validate object key pattern (uploads/{job_id}/*)
  - Extract job ID and create/update DynamoDB record
  - Send message to processing queue
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2.6 Implement status-handler
  - Create handler to query job status from DynamoDB
  - Implement API key validation
  - Return current status and progress
  - _Requirements: 6.3_

- [ ]* 2.7 Write property test for status endpoint
  - **Property 10: Status endpoint returns current state**
  - **Validates: Requirements 6.3**

- [x] 2.8 Implement result-handler
  - Create handler to retrieve completed results
  - Generate presigned URLs for avatar downloads (1-hour expiration)
  - Return complete identity package
  - _Requirements: 6.4, 6.5, 12.3_

- [ ]* 2.9 Write property test for results endpoint
  - **Property 11: Results endpoint returns complete package**
  - **Validates: Requirements 6.4, 6.5**

- [ ]* 2.10 Write property test for presigned URL expiration
  - **Property 21: Presigned URL expiration**
  - **Validates: Requirements 12.3**

- [ ]* 2.11 Write property test for API key validation
  - **Property 12: Invalid API keys are rejected**
  - **Validates: Requirements 6.6**

- [x] 3. Implement Strands Agent and tools
- [x] 3.1 Set up agent project structure
  - Create petavatar-agent directory
  - Initialize with pyproject.toml and requirements.txt
  - Create tools module structure
  - _Requirements: 9.3, 10.3_

- [x] 3.2 Implement analyze_pet_image tool
  - Create tool to analyze pet images using Claude Vision
  - Implement Bedrock API call with image input
  - Parse response to extract species, breed, expression, personality dimensions
  - Implement retry logic with exponential backoff
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 11.3_

- [ ]* 3.3 Write property test for pet analysis output structure
  - **Property 3: Pet analysis produces complete structured output**
  - **Validates: Requirements 4.1, 4.3, 4.4, 4.5**

- [ ]* 3.4 Write property test for Bedrock retry logic
  - **Property 16: Bedrock retry with exponential backoff**
  - **Validates: Requirements 11.3**

- [x] 3.5 Implement map_personality_to_career tool
  - Create tool to map personality traits to careers using Claude
  - Implement Bedrock API call with personality profile input
  - Parse response to extract job title, seniority, attire, background
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ]* 3.6 Write property test for career profile structure
  - **Property 4: Personality mapper produces valid career profiles**
  - **Validates: Requirements 5.1, 5.3, 5.4**

- [x] 3.7 Implement generate_avatar_image tool
  - Create tool to generate avatars using Titan Image Generator
  - Build prompt from career profile
  - Implement Bedrock API call to Titan
  - Validate output format and dimensions
  - Implement retry logic
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 3.8 Write property test for avatar prompt generation
  - **Property 5: Avatar generator invokes Titan with appropriate prompts**
  - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ]* 3.9 Write property test for avatar retry logic
  - **Property 6: Avatar generation retry logic**
  - **Validates: Requirements 7.4**

- [ ]* 3.10 Write property test for avatar format requirements
  - **Property 7: Generated avatars meet format requirements**
  - **Validates: Requirements 7.5**

- [x] 3.11 Implement generate_identity_package tool
  - Create tool to generate bio, skills, career trajectory using Claude
  - Implement name generation logic based on species
  - Calculate similarity score
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ]* 3.12 Write property test for identity package structure
  - **Property 8: Identity package structure completeness**
  - **Validates: Requirements 8.2, 8.3, 8.4, 8.5**

- [x] 3.13 Implement main agent orchestration
  - Create agent.py with PetAvatarAgent
  - Configure agent with all tools
  - Implement workflow orchestration
  - Add @app.entrypoint decorator for AgentCore
  - _Requirements: 9.3, 9.4_

- [x] 4. Implement process-worker Lambda function
- [x] 4.1 Create process-worker handler
  - Implement SQS message processing
  - Download image from S3
  - Invoke Strands Agent via AgentCore
  - Store generated avatar to S3
  - Update DynamoDB with results or errors
  - _Requirements: 4.5, 11.1, 11.2, 11.4_

- [ ]* 4.2 Write property test for error logging
  - **Property 14: Error logging includes context**
  - **Validates: Requirements 11.1**

- [ ]* 4.3 Write property test for error responses
  - **Property 15: Failed processing returns descriptive errors**
  - **Validates: Requirements 11.2**

- [ ]* 4.4 Write property test for timeout handling
  - **Property 17: Timeout handling**
  - **Validates: Requirements 11.4**

- [ ]* 4.5 Write property test for CloudWatch metrics
  - **Property 18: CloudWatch metrics emission**
  - **Validates: Requirements 11.5**

- [x] 5. Implement error handling and logging
- [x] 5.1 Create error handling utilities
  - Implement retry_with_exponential_backoff function
  - Create log_error function with structured logging
  - Implement emit_metric function for CloudWatch
  - _Requirements: 11.1, 11.3, 11.5_

- [x] 5.2 Add error handling to all Lambda functions
  - Wrap handlers with try-except blocks
  - Log errors with context
  - Emit CloudWatch metrics on errors
  - Return appropriate HTTP status codes
  - _Requirements: 11.1, 11.2, 11.5_

- [x] 6. Implement security configurations
- [x] 6.1 Configure S3 bucket security
  - Enable encryption at rest (AES-256)
  - Block public access
  - Configure lifecycle policies for 7-day expiration
  - _Requirements: 12.1, 12.2, 12.5_

- [ ]* 6.2 Write property test for S3 security configuration
  - **Property 19: S3 storage security configuration**
  - **Validates: Requirements 12.1, 12.5**

- [ ]* 6.3 Write property test for S3 lifecycle policies
  - **Property 20: S3 lifecycle policies**
  - **Validates: Requirements 12.2**

- [x] 6.4 Configure DynamoDB security
  - Enable encryption with AWS managed keys
  - Configure TTL for automatic cleanup
  - Set up IAM policies for least privilege access
  - _Requirements: 12.2_

- [x] 6.5 Configure API Gateway security
  - Implement API key validation
  - Configure CORS headers
  - Set up request throttling
  - _Requirements: 6.6_

- [-] 7. Deploy and configure infrastructure
- [x] 7.1 Run infrastructure provisioning scripts
  - Execute scripts/create-infrastructure.py
  - Verify DynamoDB table creation
  - Verify S3 buckets creation with correct policies
  - Verify API key in Secrets Manager
  - _Requirements: 9.1, 12.1, 12.2, 12.5_

- [x] 7.2 Deploy tc-functors topology
  - Run tc create command
  - Verify API Gateway creation
  - Verify Lambda functions deployment
  - Verify SQS queue creation
  - _Requirements: 9.1, 9.5_

- [x] 7.3 Deploy Strands Agent to AgentCore
  - Install bedrock-agentcore-starter-toolkit
  - Configure agent with agentcore configure
  - Deploy with agentcore launch
  - Capture agent ARN for Lambda configuration
  - _Requirements: 9.4_

- [x] 7.4 Configure Lambda environment variables
  - Set DYNAMODB_TABLE_NAME
  - Set S3_UPLOAD_BUCKET and S3_GENERATED_BUCKET
  - Set AGENT_RUNTIME_ARN
  - Set API_KEY_SECRET_ARN
  - _Requirements: 9.1_

- [-] 7.5 Configure S3 event notifications
  - Set up S3 event trigger for uploads bucket
  - Configure to invoke s3-event-handler Lambda
  - Test event notification delivery
  - _Requirements: 2.1_

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Integration testing and validation
- [ ] 9.1 Test presigned URL upload flow
  - Request presigned URL
  - Upload test image to S3
  - Request processing
  - Verify job status updates
  - Retrieve results
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 9.2 Test S3 event-triggered flow
  - Upload image directly to S3 with correct key pattern
  - Verify s3-event-handler invocation
  - Verify job creation in DynamoDB
  - Verify processing completion
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 9.3 Test end-to-end agent workflow
  - Trigger processing with test pet image
  - Verify all agent tools are invoked
  - Verify avatar generation
  - Verify identity package creation
  - Verify results storage in S3 and DynamoDB
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9.4 Test error scenarios
  - Test invalid image formats
  - Test oversized images
  - Test invalid API keys
  - Test Bedrock API failures
  - Test timeout scenarios
  - Verify error logging and metrics
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 9.5 Verify security configurations
  - Verify S3 buckets have public access blocked
  - Verify encryption at rest
  - Verify presigned URL expiration
  - Verify API key validation
  - Verify IAM role permissions
  - _Requirements: 12.1, 12.2, 12.3, 12.5, 6.6_

- [ ] 10. Final Checkpoint - Make sure all tests are passing
  - Ensure all tests pass, ask the user if questions arise.
