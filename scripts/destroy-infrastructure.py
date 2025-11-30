#!/usr/bin/env python3
"""
Infrastructure Cleanup Script

Destroys AWS resources created by create-infrastructure.py:
- DynamoDB table
- S3 buckets (empties them first)
- API key in Secrets Manager
"""
import boto3
import sys


def get_account_id() -> str:
    """Get AWS account ID."""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def delete_dynamodb_table(table_name: str = 'petavatar-jobs'):
    """Delete DynamoDB table."""
    dynamodb = boto3.client('dynamodb')
    
    try:
        dynamodb.delete_table(TableName=table_name)
        print(f"✓ Deleted DynamoDB table: {table_name}")
    except dynamodb.exceptions.ResourceNotFoundException:
        print(f"✓ DynamoDB table does not exist: {table_name}")


def empty_and_delete_bucket(bucket_name: str):
    """Empty and delete S3 bucket."""
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    
    try:
        # Delete all objects and versions
        bucket.object_versions.delete()
        
        # Delete the bucket
        bucket.delete()
        print(f"✓ Deleted S3 bucket: {bucket_name}")
    except Exception as e:
        if 'NoSuchBucket' in str(e):
            print(f"✓ S3 bucket does not exist: {bucket_name}")
        else:
            print(f"✗ Error deleting bucket {bucket_name}: {str(e)}")


def delete_api_key(secret_name: str = 'petavatar-api-key'):
    """Delete API key from Secrets Manager."""
    secretsmanager = boto3.client('secretsmanager')
    
    try:
        secretsmanager.delete_secret(
            SecretId=secret_name,
            ForceDeleteWithoutRecovery=True
        )
        print(f"✓ Deleted API key: {secret_name}")
    except secretsmanager.exceptions.ResourceNotFoundException:
        print(f"✓ API key does not exist: {secret_name}")


def main():
    """Main cleanup function."""
    print("PetAvatar Infrastructure Cleanup")
    print("=" * 50)
    print("WARNING: This will delete all PetAvatar infrastructure!")
    print()
    
    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cleanup cancelled.")
        sys.exit(0)
    
    try:
        # Get AWS account ID
        account_id = get_account_id()
        print(f"\nAWS Account ID: {account_id}\n")
        
        # Delete S3 buckets
        print("Deleting S3 buckets...")
        upload_bucket = f'petavatar-uploads-{account_id}'
        generated_bucket = f'petavatar-generated-{account_id}'
        
        empty_and_delete_bucket(upload_bucket)
        empty_and_delete_bucket(generated_bucket)
        print()
        
        # Delete DynamoDB table
        print("Deleting DynamoDB table...")
        delete_dynamodb_table()
        print()
        
        # Delete API key
        print("Deleting API key...")
        delete_api_key()
        print()
        
        print("=" * 50)
        print("Infrastructure cleanup complete!")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
