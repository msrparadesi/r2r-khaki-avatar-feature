"""
Presigned URL Handler
Generates presigned S3 POST URLs for direct image uploads.
"""
import json
import uuid
import os
import logging
import functools
from datetime import datetime, timezone
from typing import Dict, Any, Callable

import boto3

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def log_error(component: str, operation: str, error: Exception, context: dict) -> None:
    """Log error with structured context."""
    logger.error(json.dumps({
        "component": component,
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))


def emit_metric(metric_name: str, value: float = 1.0, dimensions: dict = None) -> None:
    """Emit CloudWatch metric."""
    try:
        cloudwatch = boto3.client('cloudwatch')
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': 'Count',
            'Timestamp': datetime.now(timezone.utc)
        }
        if dimensions:
            metric_data['Dimensions'] = [
                {'Name': k, 'Value': v} for k, v in dimensions.items()
            ]
        cloudwatch.put_metric_data(Namespace='PetAvatar', MetricData=[metric_data])
    except Exception:
        pass  # Don't fail on metric emission errors


def create_error_response(status_code: int, error_message: str, error_type: str = "Error") -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({
            'error': error_message,
            'error_type': error_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    }


def handle_lambda_errors(func: Callable) -> Callable:
    """Decorator to handle Lambda errors consistently."""
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        try:
            return func(event, context)
        except Exception as e:
            log_error(
                component=func.__name__,
                operation="handler_execution",
                error=e,
                context={"event_keys": list(event.keys()) if event else []}
            )
            emit_metric("HandlerError", dimensions={"Component": func.__name__})
            return create_error_response(500, str(e), type(e).__name__)
    return wrapper


def validate_api_key(api_key: str) -> bool:
    """Validate API key against Secrets Manager."""
    if not api_key:
        return False
    
    try:
        secret_arn = os.environ.get('API_KEY_SECRET_ARN')
        if not secret_arn:
            return True  # For local testing
        
        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        valid_key = json.loads(response['SecretString']).get('api_key')
        return api_key == valid_key
    except Exception as e:
        log_error("presigned-url-handler", "validate_api_key", e, {"has_api_key": bool(api_key)})
        return False


@handle_lambda_errors
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Generate presigned S3 URL for pet image upload."""
    # API key validation disabled for testing
    # TODO: Re-enable for production
    # headers = event.get('headers', {}) or {}
    # api_key = headers.get('x-api-key') or headers.get('X-Api-Key')
    # if not validate_api_key(api_key):
    #     emit_metric("APIKeyValidationFailure", dimensions={"Component": "presigned-url-handler"})
    #     return create_error_response(401, 'Unauthorized: Invalid API key', 'AuthenticationError')
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Get S3 bucket from environment
    upload_bucket = os.environ.get('S3_UPLOAD_BUCKET')
    if not upload_bucket:
        raise ValueError('S3_UPLOAD_BUCKET environment variable not set')
    
    # Generate S3 key for upload
    s3_key = f'uploads/{job_id}/original'
    
    # Create presigned POST URL
    s3_client = boto3.client('s3')
    presigned_post = s3_client.generate_presigned_post(
        Bucket=upload_bucket,
        Key=s3_key,
        Conditions=[
            {'bucket': upload_bucket},
            ['starts-with', '$key', f'uploads/{job_id}/'],
            ['starts-with', '$Content-Type', 'image/'],
            ['content-length-range', 1, 50 * 1024 * 1024],  # 1 byte to 50MB
        ],
        ExpiresIn=900  # 15 minutes
    )
    
    emit_metric("PresignedURLGenerated", dimensions={"Component": "presigned-url-handler"})
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({
            'job_id': job_id,
            'upload_url': presigned_post['url'],
            'upload_fields': presigned_post['fields'],
            'expires_in': 900
        })
    }
