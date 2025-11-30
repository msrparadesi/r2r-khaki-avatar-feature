#!/usr/bin/env python3
"""
Lambda Environment Variable Configuration Script

Generates the environment variable values needed for tc-functors deployment.
Run this script after infrastructure provisioning to get the values for topology.yml.

Requirements: 9.1
"""
import boto3
import sys
from typing import Dict


def get_account_id() -> str:
    """Get AWS account ID."""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def get_region() -> str:
    """Get current AWS region."""
    session = boto3.session.Session()
    return session.region_name or 'us-east-1'


def get_api_key_secret_arn(secret_name: str = 'petavatar-api-key') -> str:
    """
    Get the ARN of the API key secret from Secrets Manager.
    
    Args:
        secret_name: Name of the secret
        
    Returns:
        Secret ARN
    """
    secretsmanager = boto3.client('secretsmanager')
    
    try:
        response = secretsmanager.describe_secret(SecretId=secret_name)
        return response['ARN']
    except secretsmanager.exceptions.ResourceNotFoundException:
        print(f"⚠ Secret '{secret_name}' not found. Run create-infrastructure.py first.")
        return f"arn:aws:secretsmanager:{get_region()}:{get_account_id()}:secret:{secret_name}"


def get_sqs_queue_url(queue_name: str = 'petavatar-processing-queue') -> str:
    """
    Get the URL of the SQS processing queue.
    
    Args:
        queue_name: Name of the SQS queue
        
    Returns:
        Queue URL or placeholder if not found
    """
    sqs = boto3.client('sqs')
    region = get_region()
    account_id = get_account_id()
    
    # Try to find the queue - tc-functors may name it differently
    possible_names = [
        'petavatar-processing-queue',
        'processing-queue',
        f'petavatar-processing-queue-{account_id}'
    ]
    
    for name in possible_names:
        try:
            response = sqs.get_queue_url(QueueName=name)
            return response['QueueUrl']
        except sqs.exceptions.QueueDoesNotExist:
            continue
    
    # Return placeholder if not found
    return f"https://sqs.{region}.amazonaws.com/{account_id}/petavatar-processing-queue"


def get_agent_runtime_arn() -> str:
    """
    Get the ARN of the deployed Strands Agent.
    
    Returns:
        Agent runtime ARN (placeholder if not deployed)
    """
    # The agent ARN is obtained after deploying with agentcore launch
    # Format: arn:aws:bedrock-agentcore:{region}:{account}:runtime/{agent-id}
    region = get_region()
    account_id = get_account_id()
    
    # Check if agent is deployed by looking for the agent ID in a config file
    # For now, return a placeholder that users need to update
    return f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/AGENT_ID_PLACEHOLDER"


def verify_resources() -> Dict[str, bool]:
    """
    Verify that required AWS resources exist.
    
    Returns:
        Dictionary of resource names and their existence status
    """
    account_id = get_account_id()
    results = {}
    
    # Check DynamoDB table
    dynamodb = boto3.client('dynamodb')
    try:
        dynamodb.describe_table(TableName='petavatar-jobs')
        results['dynamodb_table'] = True
    except dynamodb.exceptions.ResourceNotFoundException:
        results['dynamodb_table'] = False
    
    # Check S3 buckets
    s3 = boto3.client('s3')
    for bucket_type in ['uploads', 'generated']:
        bucket_name = f'petavatar-{bucket_type}-{account_id}'
        try:
            s3.head_bucket(Bucket=bucket_name)
            results[f's3_{bucket_type}_bucket'] = True
        except Exception:
            results[f's3_{bucket_type}_bucket'] = False
    
    # Check Secrets Manager secret
    secretsmanager = boto3.client('secretsmanager')
    try:
        secretsmanager.describe_secret(SecretId='petavatar-api-key')
        results['api_key_secret'] = True
    except secretsmanager.exceptions.ResourceNotFoundException:
        results['api_key_secret'] = False
    
    # Check SQS queue (created by tc-functors)
    sqs = boto3.client('sqs')
    queue_found = False
    for queue_name in ['petavatar-processing-queue', 'processing-queue']:
        try:
            sqs.get_queue_url(QueueName=queue_name)
            queue_found = True
            break
        except sqs.exceptions.QueueDoesNotExist:
            continue
    results['sqs_queue'] = queue_found
    
    return results


def generate_env_file(output_file: str = '.env.petavatar') -> None:
    """
    Generate an environment file with all required values.
    
    Args:
        output_file: Path to output file
    """
    account_id = get_account_id()
    region = get_region()
    
    env_vars = {
        'DYNAMODB_TABLE_NAME': 'petavatar-jobs',
        'S3_UPLOAD_BUCKET': f'petavatar-uploads-{account_id}',
        'S3_GENERATED_BUCKET': f'petavatar-generated-{account_id}',
        'API_KEY_SECRET_ARN': get_api_key_secret_arn(),
        'AGENT_RUNTIME_ARN': get_agent_runtime_arn(),
        'SQS_QUEUE_URL': get_sqs_queue_url(),
    }
    
    with open(output_file, 'w') as f:
        f.write("# PetAvatar Lambda Environment Variables\n")
        f.write(f"# Generated for AWS Account: {account_id}\n")
        f.write(f"# Region: {region}\n\n")
        
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"✓ Environment file written to: {output_file}")


def main():
    """Main function to display environment variable configuration."""
    print("PetAvatar Lambda Environment Configuration")
    print("=" * 60)
    
    try:
        account_id = get_account_id()
        region = get_region()
        
        print(f"AWS Account ID: {account_id}")
        print(f"AWS Region: {region}")
        print()
        
        # Verify resources
        print("Verifying AWS resources...")
        resources = verify_resources()
        
        all_exist = True
        for resource, exists in resources.items():
            status = "✓" if exists else "✗"
            print(f"  {status} {resource.replace('_', ' ').title()}")
            if not exists:
                all_exist = False
        
        print()
        
        if not all_exist:
            print("⚠ Some resources are missing. Run create-infrastructure.py first.")
            print()
        
        # Display environment variables
        print("Environment Variables for topology.yml:")
        print("-" * 60)
        
        env_vars = {
            'DYNAMODB_TABLE_NAME': 'petavatar-jobs',
            'S3_UPLOAD_BUCKET': f'petavatar-uploads-{account_id}',
            'S3_GENERATED_BUCKET': f'petavatar-generated-{account_id}',
            'API_KEY_SECRET_ARN': get_api_key_secret_arn(),
            'AGENT_RUNTIME_ARN': get_agent_runtime_arn(),
            'SQS_QUEUE_URL': get_sqs_queue_url(),
        }
        
        for key, value in env_vars.items():
            print(f"  {key}={value}")
        
        print()
        print("-" * 60)
        
        # Generate .env file
        generate_env_file()
        
        print()
        print("Deployment Instructions:")
        print("-" * 60)
        print("1. Update AGENT_RUNTIME_ARN after deploying the Strands Agent:")
        print("   agentcore launch")
        print()
        print("2. Export environment variables before running tc create:")
        print("   source .env.petavatar")
        print("   # Or export individually:")
        for key, value in env_vars.items():
            print(f"   export {key}=\"{value}\"")
        print()
        print("3. Deploy the topology:")
        print("   tc create")
        print()
        print("4. Configure S3 event notifications:")
        print("   python scripts/configure-s3-events.py")
        print()
        print("5. Test S3 event notification (optional):")
        print("   python scripts/configure-s3-events.py --test")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
