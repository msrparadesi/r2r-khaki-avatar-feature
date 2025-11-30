"""
Process Handler
Validates S3 URI and initiates avatar processing.
"""
import json
import uuid
import os
import re
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, Tuple


def validate_api_key(api_key: str) -> bool:
    """
    Validate API key against Secrets Manager.
    
    Args:
        api_key: API key from request header
        
    Returns:
        True if valid, False otherwise
    """
    if not api_key:
        return False
    
    try:
        secret_arn = os.environ.get('API_KEY_SECRET_ARN')
        if not secret_arn:
            # For local testing, accept any non-empty key
            return True
        
        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        valid_key = json.loads(response['SecretString']).get('api_key')
        
        return api_key == valid_key
    except Exception:
        return False


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Parse S3 URI into bucket and key.
    
    Args:
        s3_uri: S3 URI in format s3://bucket-name/key
        
    Returns:
        Tuple of (bucket, key)
        
    Raises:
        ValueError: If URI format is invalid
    """
    # Requirement 3.1: Validate S3 URI format
    pattern = r'^s3://([^/]+)/(.+)$'
    match = re.match(pattern, s3_uri)
    
    if not match:
        raise ValueError('Invalid S3 URI format. Expected: s3://bucket-name/key')
    
    bucket = match.group(1)
    key = match.group(2)
    
    return bucket, key


def validate_s3_object(bucket: str, key: str) -> Dict[str, Any]:
    """
    Verify S3 object exists and validate format/size.
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Object metadata
        
    Raises:
        ValueError: If object doesn't exist or validation fails
    """
    s3_client = boto3.client('s3')
    
    try:
        # Requirement 3.2: Verify S3 object exists
        response = s3_client.head_object(Bucket=bucket, Key=key)
    except s3_client.exceptions.NoSuchKey:
        raise ValueError(f'S3 object not found: s3://{bucket}/{key}')
    except Exception as e:
        raise ValueError(f'Error accessing S3 object: {str(e)}')
    
    # Requirement 3.3: Validate format and size
    content_type = response.get('ContentType', '')
    content_length = response.get('ContentLength', 0)
    
    # Validate format (JPEG, PNG, HEIC)
    valid_types = ['image/jpeg', 'image/png', 'image/heic']
    if content_type not in valid_types:
        raise ValueError(
            f'Invalid image format: {content_type}. '
            f'Supported formats: JPEG, PNG, HEIC'
        )
    
    # Validate size (<50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    if content_length > max_size:
        raise ValueError(
            f'Image too large: {content_length} bytes. '
            f'Maximum size: {max_size} bytes (50MB)'
        )
    
    return response


def extract_job_id(key: str) -> str:
    """
    Extract job ID from S3 key or generate new one.
    
    Args:
        key: S3 object key
        
    Returns:
        Job ID
    """
    # Try to extract job ID from key pattern: uploads/{job_id}/...
    pattern = r'uploads/([^/]+)/'
    match = re.match(pattern, key)
    
    if match:
        return match.group(1)
    
    # Generate new job ID if pattern doesn't match
    return str(uuid.uuid4())


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Initiate processing for an uploaded pet image.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 6.2
    """
    try:
        # Validate API key
        api_key = event.get('headers', {}).get('x-api-key')
        if not validate_api_key(api_key):
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Unauthorized: Invalid API key'})
            }
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        s3_uri = body.get('s3_uri')
        
        if not s3_uri:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Missing s3_uri parameter'})
            }
        
        # Parse and validate S3 URI
        try:
            bucket, key = parse_s3_uri(s3_uri)
        except ValueError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': str(e)})
            }
        
        # Verify object exists and validate format/size
        try:
            validate_s3_object(bucket, key)
        except ValueError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': str(e)})
            }
        
        # Extract or generate job ID
        job_id = extract_job_id(key)
        
        # Get environment variables
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        queue_url = os.environ.get('SQS_QUEUE_URL')
        
        if not table_name or not queue_url:
            raise ValueError('Missing required environment variables')
        
        # Requirement 3.4: Create DynamoDB record with status "queued"
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)  # 7 days
        
        table.put_item(
            Item={
                'job_id': job_id,
                'status': 'queued',
                'created_at': timestamp,
                'updated_at': timestamp,
                's3_upload_key': key,
                'progress': 0,
                'ttl': ttl
            }
        )
        
        # Requirement 3.4: Send message to SQS queue
        sqs_client = boto3.client('sqs')
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({
                'job_id': job_id,
                's3_upload_key': key,
                'timestamp': timestamp
            })
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'job_id': job_id,
                'status': 'queued',
                'message': 'Processing initiated'
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
