#!/usr/bin/env python3
"""
S3 Event Notification Configuration Script

Configures S3 event notifications to trigger the s3-event-handler Lambda
when images are uploaded to the uploads bucket.

Requirements: 2.1
"""
import boto3
import sys
from typing import Dict, Any, Optional


def get_account_id() -> str:
    """Get AWS account ID."""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def get_region() -> str:
    """Get current AWS region."""
    session = boto3.session.Session()
    return session.region_name or 'us-east-1'


def get_lambda_function_arn(function_name: str) -> Optional[str]:
    """
    Get the ARN of a Lambda function.
    
    Args:
        function_name: Name of the Lambda function
        
    Returns:
        Function ARN or None if not found
    """
    lambda_client = boto3.client('lambda')
    
    try:
        response = lambda_client.get_function(FunctionName=function_name)
        return response['Configuration']['FunctionArn']
    except lambda_client.exceptions.ResourceNotFoundException:
        return None


def find_s3_event_handler_function() -> Optional[str]:
    """
    Find the s3-event-handler Lambda function deployed by tc-functors.
    
    tc-functors names functions with the topology name prefix.
    Expected pattern: petavatar-s3-event-handler
    
    Returns:
        Function ARN or None if not found
    """
    lambda_client = boto3.client('lambda')
    
    # Possible function name patterns
    possible_names = [
        'petavatar-s3-event-handler',
        's3-event-handler',
        'petavatar_s3_event_handler',
        's3_event_handler'
    ]
    
    # Try each possible name
    for name in possible_names:
        arn = get_lambda_function_arn(name)
        if arn:
            return arn
    
    # List all functions and search for matching pattern
    try:
        paginator = lambda_client.get_paginator('list_functions')
        for page in paginator.paginate():
            for func in page['Functions']:
                func_name = func['FunctionName'].lower()
                if 's3-event-handler' in func_name or 's3_event_handler' in func_name:
                    return func['FunctionArn']
    except Exception as e:
        print(f"Warning: Could not list Lambda functions: {e}")
    
    return None


def add_lambda_permission(
    function_arn: str,
    bucket_name: str,
    account_id: str
) -> bool:
    """
    Add permission for S3 to invoke the Lambda function.
    
    Args:
        function_arn: ARN of the Lambda function
        bucket_name: Name of the S3 bucket
        account_id: AWS account ID
        
    Returns:
        True if permission was added or already exists
    """
    lambda_client = boto3.client('lambda')
    statement_id = f's3-invoke-{bucket_name.replace("-", "")}'
    
    try:
        lambda_client.add_permission(
            FunctionName=function_arn,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com',
            SourceArn=f'arn:aws:s3:::{bucket_name}',
            SourceAccount=account_id
        )
        print(f"✓ Added Lambda permission for S3 bucket: {bucket_name}")
        return True
    except lambda_client.exceptions.ResourceConflictException:
        print(f"✓ Lambda permission already exists for S3 bucket: {bucket_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to add Lambda permission: {e}")
        return False


def configure_s3_event_notification(
    bucket_name: str,
    lambda_arn: str
) -> bool:
    """
    Configure S3 bucket event notification to trigger Lambda.
    
    Args:
        bucket_name: Name of the S3 bucket
        lambda_arn: ARN of the Lambda function to invoke
        
    Returns:
        True if configuration was successful
    """
    s3_client = boto3.client('s3')
    
    # Define the notification configuration
    # Requirement 2.1: Trigger on object creation in uploads/ prefix
    notification_config = {
        'LambdaFunctionConfigurations': [
            {
                'Id': 'PetAvatarUploadTrigger',
                'LambdaFunctionArn': lambda_arn,
                'Events': [
                    's3:ObjectCreated:*'
                ],
                'Filter': {
                    'Key': {
                        'FilterRules': [
                            {
                                'Name': 'prefix',
                                'Value': 'uploads/'
                            }
                        ]
                    }
                }
            }
        ]
    }
    
    try:
        s3_client.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration=notification_config
        )
        print(f"✓ Configured S3 event notification for bucket: {bucket_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to configure S3 event notification: {e}")
        return False


def verify_s3_event_notification(bucket_name: str) -> Dict[str, Any]:
    """
    Verify S3 event notification configuration.
    
    Args:
        bucket_name: Name of the S3 bucket
        
    Returns:
        Current notification configuration
    """
    s3_client = boto3.client('s3')
    
    try:
        response = s3_client.get_bucket_notification_configuration(
            Bucket=bucket_name
        )
        return response
    except Exception as e:
        print(f"✗ Failed to get notification configuration: {e}")
        return {}


def test_event_notification(bucket_name: str, job_id: str = 'test-job-123') -> bool:
    """
    Test S3 event notification by uploading a test file.
    
    Args:
        bucket_name: Name of the S3 bucket
        job_id: Test job ID
        
    Returns:
        True if test file was uploaded successfully
    """
    s3_client = boto3.client('s3')
    
    test_key = f'uploads/{job_id}/test.txt'
    test_content = b'Test file for S3 event notification'
    
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        print(f"✓ Uploaded test file: s3://{bucket_name}/{test_key}")
        print("  Check CloudWatch Logs for s3-event-handler to verify trigger")
        return True
    except Exception as e:
        print(f"✗ Failed to upload test file: {e}")
        return False


def cleanup_test_file(bucket_name: str, job_id: str = 'test-job-123') -> bool:
    """
    Clean up test file after verification.
    
    Args:
        bucket_name: Name of the S3 bucket
        job_id: Test job ID
        
    Returns:
        True if cleanup was successful
    """
    s3_client = boto3.client('s3')
    
    test_key = f'uploads/{job_id}/test.txt'
    
    try:
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=test_key
        )
        print(f"✓ Cleaned up test file: s3://{bucket_name}/{test_key}")
        return True
    except Exception as e:
        print(f"⚠ Failed to clean up test file: {e}")
        return False


def main():
    """Main function to configure S3 event notifications."""
    print("PetAvatar S3 Event Notification Configuration")
    print("=" * 60)
    
    try:
        account_id = get_account_id()
        region = get_region()
        
        print(f"AWS Account ID: {account_id}")
        print(f"AWS Region: {region}")
        print()
        
        # Determine bucket name
        bucket_name = f'petavatar-uploads-{account_id}'
        
        # Verify bucket exists
        s3_client = boto3.client('s3')
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"✓ Found S3 bucket: {bucket_name}")
        except Exception:
            print(f"✗ S3 bucket not found: {bucket_name}")
            print("  Run create-infrastructure.py first.")
            sys.exit(1)
        
        print()
        
        # Find the Lambda function
        print("Finding s3-event-handler Lambda function...")
        lambda_arn = find_s3_event_handler_function()
        
        if not lambda_arn:
            print("✗ s3-event-handler Lambda function not found.")
            print("  Deploy the tc-functors topology first: tc create")
            sys.exit(1)
        
        print(f"✓ Found Lambda function: {lambda_arn}")
        print()
        
        # Add Lambda permission for S3
        print("Configuring Lambda permission...")
        if not add_lambda_permission(lambda_arn, bucket_name, account_id):
            print("✗ Failed to add Lambda permission")
            sys.exit(1)
        
        print()
        
        # Configure S3 event notification
        print("Configuring S3 event notification...")
        if not configure_s3_event_notification(bucket_name, lambda_arn):
            print("✗ Failed to configure S3 event notification")
            sys.exit(1)
        
        print()
        
        # Verify configuration
        print("Verifying configuration...")
        config = verify_s3_event_notification(bucket_name)
        
        if config.get('LambdaFunctionConfigurations'):
            print("✓ S3 event notification configured successfully")
            print()
            print("Configuration details:")
            for cfg in config['LambdaFunctionConfigurations']:
                print(f"  - ID: {cfg.get('Id')}")
                print(f"    Events: {cfg.get('Events')}")
                print(f"    Lambda: {cfg.get('LambdaFunctionArn')}")
                if 'Filter' in cfg:
                    rules = cfg['Filter'].get('Key', {}).get('FilterRules', [])
                    for rule in rules:
                        print(f"    Filter: {rule.get('Name')}={rule.get('Value')}")
        else:
            print("⚠ No Lambda function configurations found")
        
        print()
        print("=" * 60)
        print("S3 Event Notification Configuration Complete!")
        print()
        print("Testing:")
        print("-" * 60)
        print("To test the event notification:")
        print(f"  1. Upload a file to s3://{bucket_name}/uploads/<job_id>/")
        print("  2. Check CloudWatch Logs for the s3-event-handler function")
        print("  3. Verify the job appears in DynamoDB petavatar-jobs table")
        print()
        print("Or run this script with --test flag:")
        print("  python scripts/configure-s3-events.py --test")
        
        # Handle --test flag
        if len(sys.argv) > 1 and sys.argv[1] == '--test':
            print()
            print("Running test...")
            print("-" * 60)
            test_event_notification(bucket_name)
            print()
            print("Waiting 5 seconds for Lambda to process...")
            import time
            time.sleep(5)
            cleanup_test_file(bucket_name)
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
