"""
Presigned URL Handler
Generates presigned S3 POST URLs for direct image uploads.
"""
import json
import uuid
import os
import boto3
from typing import Dict, Any


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
        # If we can't validate, reject for security
        return False


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate presigned S3 URL for pet image upload.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 6.1
    """
    try:
        # Validate API key from headers
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
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Get S3 bucket from environment
        upload_bucket = os.environ.get('S3_UPLOAD_BUCKET')
        if not upload_bucket:
            raise ValueError('S3_UPLOAD_BUCKET environment variable not set')
        
        # Generate S3 key for upload
        s3_key = f'uploads/{job_id}/original'
        
        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Generate presigned POST URL with conditions
        # Requirements: 1.1 (15-minute expiration), 1.2 (format restrictions), 1.3 (50MB limit)
        presigned_post = s3_client.generate_presigned_post(
            Bucket=upload_bucket,
            Key=s3_key,
            Fields={
                'Content-Type': '${filename}'
            },
            Conditions=[
                {'bucket': upload_bucket},
                ['starts-with', '$key', f'uploads/{job_id}/'],
                ['starts-with', '$Content-Type', 'image/'],
                ['content-length-range', 1, 50 * 1024 * 1024],  # 1 byte to 50MB
                # Accept JPEG, PNG, HEIC formats
                ['eq', '$Content-Type', 'image/jpeg'],
                ['eq', '$Content-Type', 'image/png'],
                ['eq', '$Content-Type', 'image/heic']
            ],
            ExpiresIn=900  # 15 minutes
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'job_id': job_id,
                'upload_url': presigned_post['url'],
                'upload_fields': presigned_post['fields'],
                'expires_in': 900
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
