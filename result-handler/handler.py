"""
Result Handler
Returns completed identity package with presigned URLs.
"""
import json
import os
import sys
import boto3
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
from src.utils import (
    handle_lambda_errors,
    log_error,
    emit_metric,
    create_error_response
)


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
    except Exception as e:
        log_error(
            component="result-handler",
            operation="validate_api_key",
            error=e,
            context={"has_api_key": bool(api_key)}
        )
        return False


@handle_lambda_errors
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Retrieve completed avatar results.
    
    Requirements: 6.4, 6.5, 12.3
    Validates: Requirements 11.1, 11.2, 11.5
    """
    # API key validation disabled for testing
    # TODO: Re-enable for production
    # api_key = event.get('headers', {}).get('x-api-key')
    # if not validate_api_key(api_key):
    #     emit_metric("APIKeyValidationFailure", dimensions={"Component": "result-handler"})
    #     return create_error_response(status_code=401, error_message='Unauthorized: Invalid API key', error_type='AuthenticationError')
    
    # Extract job_id from path parameters
    job_id = event.get('pathParameters', {}).get('job_id')
    
    if not job_id:
        emit_metric(
            "ValidationError",
            dimensions={"Component": "result-handler", "ErrorType": "MissingParameter"}
        )
        return create_error_response(
            status_code=400,
            error_message='Missing job_id parameter',
            error_type='ValidationError'
        )
    
    # Get environment variables
    table_name = os.environ.get('DYNAMODB_TABLE_NAME')
    generated_bucket = os.environ.get('S3_GENERATED_BUCKET')
    
    if not table_name or not generated_bucket:
        log_error(
            component="result-handler",
            operation="get_environment_config",
            error=ValueError('Missing environment variables'),
            context={"job_id": job_id}
        )
        emit_metric(
            "ConfigurationError",
            dimensions={"Component": "result-handler"}
        )
        raise ValueError('Missing required environment variables')
    
    # Query DynamoDB for job
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    response = table.get_item(Key={'job_id': job_id})
    
    if 'Item' not in response:
        emit_metric(
            "JobNotFound",
            dimensions={"Component": "result-handler"}
        )
        return create_error_response(
            status_code=404,
            error_message=f'Job not found: {job_id}',
            error_type='NotFoundError'
        )
    
    item = response['Item']
    
    # Check status is "completed"
    if item.get('status') != 'completed':
        emit_metric(
            "JobNotCompleted",
            dimensions={"Component": "result-handler", "Status": item.get('status', 'unknown')}
        )
        return create_error_response(
            status_code=409,
            error_message=f'Job not completed. Current status: {item.get("status")}',
            error_type='ConflictError',
            details={'status': item.get('status'), 'progress': item.get('progress', 0)}
        )
    
    # Generate presigned URL for avatar (1 hour expiration)
    s3_client = boto3.client('s3')
    avatar_key = item.get('s3_avatar_key')
    
    if not avatar_key:
        log_error(
            component="result-handler",
            operation="get_avatar_key",
            error=ValueError('Avatar key not found in DynamoDB'),
            context={"job_id": job_id}
        )
        emit_metric(
            "MissingAvatarKey",
            dimensions={"Component": "result-handler"}
        )
        return create_error_response(
            status_code=500,
            error_message='Avatar image not found',
            error_type='InternalError'
        )
    
    try:
        avatar_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': generated_bucket,
                'Key': avatar_key
            },
            ExpiresIn=3600  # 1 hour
        )
    except Exception as e:
        log_error(
            component="result-handler",
            operation="generate_presigned_url",
            error=e,
            context={"job_id": job_id, "avatar_key": avatar_key}
        )
        emit_metric(
            "PresignedURLError",
            dimensions={"Component": "result-handler"}
        )
        raise
    
    # Build complete identity package
    result = {
        'job_id': job_id,
        'avatar_url': avatar_url,
        'identity': item.get('identity_package', {}),
        'pet_analysis': item.get('pet_analysis', {})
    }
    
    # Emit success metric
    emit_metric(
        "ResultsRetrieved",
        dimensions={"Component": "result-handler"}
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(result)
    }
