"""
S3 Event Handler
Handles S3 upload event notifications and initiates processing.
"""
import json
import os
import re
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def validate_object_key(key: str) -> Optional[str]:
    """
    Validate object key matches expected pattern and extract job ID.
    
    Args:
        key: S3 object key
        
    Returns:
        Job ID if valid, None otherwise
    """
    # Requirement 2.2: Validate object key pattern (uploads/{job_id}/*)
    pattern = r'^uploads/([^/]+)/.+$'
    match = re.match(pattern, key)
    
    if not match:
        return None
    
    job_id = match.group(1)
    return job_id


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process S3 upload events and queue for avatar generation.
    
    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    try:
        # Get environment variables
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        queue_url = os.environ.get('SQS_QUEUE_URL')
        
        if not table_name or not queue_url:
            raise ValueError('Missing required environment variables')
        
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        sqs_client = boto3.client('sqs')
        
        # Requirement 2.1: Process S3 event notification
        for record in event.get('Records', []):
            # Extract S3 information
            s3_info = record.get('s3', {})
            bucket_name = s3_info.get('bucket', {}).get('name')
            object_key = s3_info.get('object', {}).get('key')
            
            if not bucket_name or not object_key:
                print(f'Invalid S3 event record: {record}')
                continue
            
            # Validate object key and extract job ID
            job_id = validate_object_key(object_key)
            
            if not job_id:
                # Requirement 2.5: Log invalid events and take no further action
                print(f'Invalid object key pattern, ignoring: {object_key}')
                continue
            
            timestamp = datetime.now(timezone.utc).isoformat()
            ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)  # 7 days
            
            # Requirement 2.3: Create DynamoDB record if it doesn't exist
            try:
                # Try to get existing item
                response = table.get_item(Key={'job_id': job_id})
                
                if 'Item' not in response:
                    # Create new record
                    table.put_item(
                        Item={
                            'job_id': job_id,
                            'status': 'queued',
                            'created_at': timestamp,
                            'updated_at': timestamp,
                            's3_upload_key': object_key,
                            'progress': 0,
                            'ttl': ttl
                        }
                    )
                    print(f'Created DynamoDB record for job {job_id}')
                else:
                    # Update existing record
                    table.update_item(
                        Key={'job_id': job_id},
                        UpdateExpression='SET updated_at = :timestamp, s3_upload_key = :key',
                        ExpressionAttributeValues={
                            ':timestamp': timestamp,
                            ':key': object_key
                        }
                    )
                    print(f'Updated DynamoDB record for job {job_id}')
            except Exception as e:
                print(f'Error updating DynamoDB for job {job_id}: {str(e)}')
                continue
            
            # Requirement 2.4: Send message to processing queue
            try:
                sqs_client.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({
                        'job_id': job_id,
                        's3_upload_key': object_key,
                        'timestamp': timestamp
                    })
                )
                print(f'Sent SQS message for job {job_id}')
            except Exception as e:
                print(f'Error sending SQS message for job {job_id}: {str(e)}')
                continue
            
            print(f'Successfully processed S3 event: s3://{bucket_name}/{object_key}')
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Events processed'})
        }
    except Exception as e:
        print(f'Error processing S3 event: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
