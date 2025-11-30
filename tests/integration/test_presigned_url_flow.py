"""Integration tests for presigned URL upload flow. Req: 1.1-1.4, 3.1-3.4, 6.1-6.5"""
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


class TestPresignedURLHandler:
    def test_generates_presigned_url_with_valid_api_key(self):
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_post.return_value = {
                'url': 'https://test-bucket.s3.amazonaws.com',
                'fields': {'key': 'uploads/test-job-id/original'}
            }
            mock_boto_client.return_value = mock_s3
            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': 'valid-test-key'}}
                context = MockContext('presigned-url-handler')
                response = module.handler(event, context)
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'job_id' in body
            assert body['expires_in'] == 900

    def test_rejects_missing_api_key(self):
        with patch('boto3.client'):
            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {}}
                context = MockContext('presigned-url-handler')
                response = module.handler(event, context)
            assert response['statusCode'] == 401


class TestProcessHandler:
    def test_rejects_invalid_s3_uri_format(self):
        with patch('boto3.client'):
            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {'headers': {'x-api-key': 'k'}, 'body': json.dumps({'s3_uri': 'invalid'})}
                response = module.handler(event, MockContext('process-handler'))
            assert response['statusCode'] == 400


class TestStatusHandler:
    def test_returns_job_status(self):
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
            assert response['statusCode'] == 200
            assert json.loads(response['body'])['status'] == 'processing'

    def test_returns_404_for_unknown_job(self):
        with patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            module = load_handler_module('status-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table'}):
                event = {'headers': {'x-api-key': 'k'}, 'pathParameters': {'job_id': 'unknown'}}
                response = module.handler(event, MockContext('status-handler'))
            assert response['statusCode'] == 404



class TestResultHandler:
    def test_returns_complete_identity_package(self):
        with patch('boto3.client') as mock_boto_client, patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {
                'Item': {
                    'job_id': 'j1', 'status': 'completed', 's3_avatar_key': 'g/j1/a.png',
                    'identity_package': {'human_name': 'Greg'}, 'pet_analysis': {'species': 'dog'}
                }
            }
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = 'https://url'
            mock_boto_client.return_value = mock_s3
            module = load_handler_module('result-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'S3_GENERATED_BUCKET': 'b'}):
                event = {'headers': {'x-api-key': 'k'}, 'pathParameters': {'job_id': 'j1'}}
                response = module.handler(event, MockContext('result-handler'))
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'avatar_url' in body
            assert 'identity' in body

    def test_returns_409_for_incomplete_job(self):
        with patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': {'job_id': 'j1', 'status': 'processing', 'progress': 50}}
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            module = load_handler_module('result-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'S3_GENERATED_BUCKET': 'b'}):
                event = {'headers': {'x-api-key': 'k'}, 'pathParameters': {'job_id': 'j1'}}
                response = module.handler(event, MockContext('result-handler'))
            assert response['statusCode'] == 409
