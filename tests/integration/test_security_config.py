"""Integration tests for security configurations. Req: 12.1, 12.2, 12.3, 12.5, 6.6"""
import json
import os
import sys
import uuid
import importlib.util
from unittest.mock import MagicMock, patch
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


def load_handler_module(handler_dir: str) -> Any:
    handler_path = os.path.join(PROJECT_ROOT, handler_dir, 'handler.py')
    spec = importlib.util.spec_from_file_location(f"{handler_dir.replace('-', '_')}_mod", handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MockContext:
    def __init__(self, function_name: str = "test-function"):
        self.function_name = function_name
        self.aws_request_id = str(uuid.uuid4())
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = f"arn:aws:lambda:us-east-1:123456789:function:{function_name}"


class TestAPIKeyValidation:
    """Tests for API key validation. Req: 6.6"""

    def test_presigned_url_requires_api_key(self):
        """Test presigned URL endpoint requires API key."""
        with patch('boto3.client'):
            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {}}
                response = module.handler(event, MockContext('presigned-url-handler'))
            assert response['statusCode'] == 401

    def test_process_endpoint_requires_api_key(self):
        """Test process endpoint requires API key."""
        with patch('boto3.client'):
            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'q'}):
                event = {'headers': {}, 'body': json.dumps({'s3_uri': 's3://b/k'})}
                response = module.handler(event, MockContext('process-handler'))
            assert response['statusCode'] == 401

    def test_status_endpoint_requires_api_key(self):
        """Test status endpoint requires API key."""
        with patch('boto3.resource'):
            module = load_handler_module('status-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table'}):
                event = {'headers': {}, 'pathParameters': {'job_id': 'test'}}
                response = module.handler(event, MockContext('status-handler'))
            assert response['statusCode'] == 401


    def test_results_endpoint_requires_api_key(self):
        """Test results endpoint requires API key."""
        with patch('boto3.resource'), patch('boto3.client'):
            module = load_handler_module('result-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'S3_GENERATED_BUCKET': 'b'}):
                event = {'headers': {}, 'pathParameters': {'job_id': 'test'}}
                response = module.handler(event, MockContext('result-handler'))
            assert response['statusCode'] == 401


class TestPresignedURLExpiration:
    """Tests for presigned URL expiration. Req: 12.3"""

    def test_upload_presigned_url_expires_in_15_minutes(self):
        """Test upload presigned URL has 15-minute expiration."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_post.return_value = {'url': 'https://s3', 'fields': {}}
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': 'valid-key'}}
                response = module.handler(event, MockContext('presigned-url-handler'))

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['expires_in'] == 900  # 15 minutes

            # Verify S3 was called with correct expiration
            call_args = mock_s3.generate_presigned_post.call_args
            assert call_args.kwargs.get('ExpiresIn') == 900

    def test_download_presigned_url_expires_in_1_hour(self):
        """Test download presigned URL has 1-hour expiration."""
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {
                'Item': {
                    'job_id': 'j1', 'status': 'completed',
                    's3_avatar_key': 'g/j1/a.png',
                    'identity_package': {}, 'pet_analysis': {}
                }
            }
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = 'https://presigned'
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('result-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'S3_GENERATED_BUCKET': 'b'}):
                event = {'headers': {'x-api-key': 'k'}, 'pathParameters': {'job_id': 'j1'}}
                module.handler(event, MockContext('result-handler'))

            # Verify S3 was called with 1-hour expiration
            call_args = mock_s3.generate_presigned_url.call_args
            assert call_args.kwargs.get('ExpiresIn') == 3600  # 1 hour



class TestCORSHeaders:
    """Tests for CORS headers. Req: 6.6"""

    def test_presigned_url_response_includes_cors_headers(self):
        """Test presigned URL response includes CORS headers."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_post.return_value = {'url': 'https://s3', 'fields': {}}
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': 'valid-key'}}
                response = module.handler(event, MockContext('presigned-url-handler'))

            assert 'headers' in response
            headers = response['headers']
            assert 'Access-Control-Allow-Origin' in headers
            assert 'Access-Control-Allow-Headers' in headers

    def test_status_response_includes_cors_headers(self):
        """Test status response includes CORS headers."""
        with patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': {'job_id': 'j1', 'status': 'processing', 'progress': 50}}
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            module = load_handler_module('status-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table'}):
                event = {'headers': {'x-api-key': 'k'}, 'pathParameters': {'job_id': 'j1'}}
                response = module.handler(event, MockContext('status-handler'))

            assert 'headers' in response
            headers = response['headers']
            assert 'Access-Control-Allow-Origin' in headers


class TestS3SecurityConfiguration:
    """Tests for S3 security configuration verification. Req: 12.1, 12.5"""

    def test_presigned_url_enforces_content_type_restrictions(self):
        """Test presigned URL enforces content type restrictions."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': 'valid-key'}}
                module.handler(event, MockContext('presigned-url-handler'))

            # Verify generate_presigned_post was called with content type conditions
            call_args = mock_s3.generate_presigned_post.call_args
            conditions = call_args.kwargs.get('Conditions', [])
            # Check for content-type related conditions
            content_conditions = [c for c in conditions if 'Content-Type' in str(c) or 'content' in str(c).lower()]
            assert len(content_conditions) > 0

    def test_presigned_url_enforces_size_restrictions(self):
        """Test presigned URL enforces size restrictions."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': 'valid-key'}}
                module.handler(event, MockContext('presigned-url-handler'))

            # Verify generate_presigned_post was called with size limit
            call_args = mock_s3.generate_presigned_post.call_args
            conditions = call_args.kwargs.get('Conditions', [])
            # Check for content-length-range condition
            size_conditions = [c for c in conditions if 'content-length-range' in str(c)]
            assert len(size_conditions) > 0
