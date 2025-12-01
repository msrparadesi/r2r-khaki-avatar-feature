"""
Status Handler
Returns current processing status for a job.
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
            component="status-handler",
            operation="validate_api_key",
            error=e,
            context={"has_api_key": bool(api_key)}
        )
        return False


@handle_lambda_errors
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Query job status from DynamoDB.
    
    Requirements: 6.3
    Validates: Requirements 11.1, 11.2, 11.5
    """
    # API key validation disabled for testing
    # TODO: Re-enable for production
    # api_key = event.get('headers', {}).get('x-api-key')
    # if not validate_api_key(api_key):
    #     emit_metric("APIKeyValidationFailure", dimensions={"Component": "status-handler"})
    #     return create_error_response(status_code=401, error_message='Unauthorized: Invalid API key', error_type='AuthenticationError')
    
    # Extract job_id from path parameters
    job_id = event.get('pathParameters', {}).get('job_id')
    
    if not job_id:
        emit_metric(
            "ValidationError",
            dimensions={"Component": "status-handler", "ErrorType": "MissingParameter"}
        )
        return create_error_response(
            status_code=400,
            error_message='Missing job_id parameter',
            error_type='ValidationError'
        )
    
    # Get DynamoDB table name from environment
    table_name = os.environ.get('DYNAMODB_TABLE_NAME')
    if not table_name:
        log_error(
            component="status-handler",
            operation="get_environment_config",
            error=ValueError('DYNAMODB_TABLE_NAME not configured'),
            context={"job_id": job_id}
        )
        emit_metric(
            "ConfigurationError",
            dimensions={"Component": "status-handler"}
        )
        raise ValueError('DYNAMODB_TABLE_NAME environment variable not set')
    
    # Query DynamoDB for job status
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    response = table.get_item(Key={'job_id': job_id})
    
    if 'Item' not in response:
        emit_metric(
            "JobNotFound",
            dimensions={"Component": "status-handler"}
        )
        return create_error_response(
            status_code=404,
            error_message=f'Job not found: {job_id}',
            error_type='NotFoundError'
        )
    
    item = response['Item']
    
    # Build response with status and progress
    result = {
        'job_id': job_id,
        'status': item.get('status', 'unknown'),
        'progress': item.get('progress', 0)
    }
    
    # Include error message if status is failed
    if item.get('status') == 'failed' and 'error_message' in item:
        result['error'] = item['error_message']
    
    # Emit success metric
    emit_metric(
        "StatusQuerySuccess",
        dimensions={"Component": "status-handler", "Status": item.get('status', 'unknown')}
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
