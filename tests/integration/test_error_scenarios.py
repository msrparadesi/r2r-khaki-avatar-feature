"""Integration tests for error scenarios. Req: 11.1, 11.2, 11.3, 11.4, 11.5"""
import json
import os
import sys
import uuid
import importlib.util
from unittest.mock import MagicMock, patch
from typing import Any
from botocore.exceptions import ClientError

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


class TestInvalidImageFormats:
    """Tests for invalid image format handling. Req: 11.2"""

    def test_rejects_gif_format(self):
        """Test GIF format rejection."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.head_object.return_value = {'ContentType': 'image/gif', 'ContentLength': 1024}
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'headers': {'x-api-key': 'k'},
                    'body': json.dumps({'s3_uri': 's3://bucket/uploads/job/image.gif'})
                }
                response = module.handler(event, MockContext('process-handler'))

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'Invalid image format' in body['error']



class TestOversizedImages:
    """Tests for oversized image handling. Req: 11.2"""

    def test_rejects_images_over_50mb(self):
        """Test rejection of images over 50MB."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            mock_s3.head_object.return_value = {
                'ContentType': 'image/jpeg',
                'ContentLength': 60 * 1024 * 1024  # 60MB
            }
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'headers': {'x-api-key': 'k'},
                    'body': json.dumps({'s3_uri': 's3://bucket/uploads/job/large.jpg'})
                }
                response = module.handler(event, MockContext('process-handler'))

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'too large' in body['error'].lower()


class TestInvalidAPIKeys:
    """Tests for invalid API key handling. Req: 6.6, 11.2"""

    def test_rejects_empty_api_key(self):
        """Test empty API key rejection."""
        with patch('boto3.client'):
            module = load_handler_module('presigned-url-handler')
            with patch.dict(os.environ, {'S3_UPLOAD_BUCKET': 'test-bucket'}):
                event = {'headers': {'x-api-key': ''}}
                response = module.handler(event, MockContext('presigned-url-handler'))

            assert response['statusCode'] == 401
            body = json.loads(response['body'])
            assert 'Unauthorized' in body['error']

    def test_rejects_missing_api_key_header(self):
        """Test missing API key header rejection."""
        with patch('boto3.client'):
            module = load_handler_module('status-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table'}):
                event = {'headers': {}, 'pathParameters': {'job_id': 'test-job'}}
                response = module.handler(event, MockContext('status-handler'))

            assert response['statusCode'] == 401


class TestBedrockAPIFailures:
    """Tests for Bedrock API failure handling. Req: 11.3"""

    def test_handles_bedrock_throttling(self):
        """Test Bedrock throttling error handling."""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {'Body': MagicMock(read=lambda: b'fake-image')}

            # Mock Bedrock to raise throttling error
            mock_bedrock = MagicMock()
            throttle_error = ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'InvokeAgent'
            )
            mock_bedrock.invoke_agent.side_effect = throttle_error

            def client_factory(service):
                if service == 's3':
                    return mock_s3
                elif service == 'bedrock-agent-runtime':
                    return mock_bedrock
                return MagicMock()

            mock_boto_client.side_effect = client_factory

            module = load_handler_module('process-worker')
            with patch.dict(os.environ, {
                'DYNAMODB_TABLE_NAME': 'test-table',
                'S3_UPLOAD_BUCKET': 'test-upload-bucket',
                'S3_GENERATED_BUCKET': 'test-generated-bucket',
                'AGENT_RUNTIME_ARN': 'arn:aws:bedrock-agentcore:us-east-1:123:runtime/test-agent'
            }):
                event = {
                    'Records': [{
                        'body': json.dumps({
                            'job_id': 'test-job-id',
                            's3_upload_key': 'uploads/test-job-id/image.jpg'
                        })
                    }]
                }
                response = module.handler(event, MockContext('process-worker'))

            # Should return error status
            assert response['statusCode'] == 500



class TestErrorLogging:
    """Tests for error logging. Req: 11.1"""

    def test_logs_errors_with_context(self):
        """Test that errors are logged with sufficient context."""
        with patch('boto3.client') as mock_boto_client, \
             patch('src.utils.error_handling.logger') as mock_logger:
            mock_s3 = MagicMock()
            mock_s3.head_object.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'}},
                'HeadObject'
            )
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'headers': {'x-api-key': 'k'},
                    'body': json.dumps({'s3_uri': 's3://bucket/uploads/job/missing.jpg'})
                }
                module.handler(event, MockContext('process-handler'))

            # Verify error was logged (logger.error or logger.log was called)
            assert mock_logger.error.called or mock_logger.log.called


class TestErrorResponses:
    """Tests for descriptive error responses. Req: 11.2"""

    def test_returns_descriptive_error_for_missing_s3_object(self):
        """Test descriptive error for missing S3 object."""
        with patch('boto3.client') as mock_boto_client:
            mock_s3 = MagicMock()
            # Simulate S3 object not found by raising exception in validate_s3_object
            mock_s3.head_object.side_effect = Exception("S3 object not found")
            mock_boto_client.return_value = mock_s3

            module = load_handler_module('process-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 't', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'headers': {'x-api-key': 'k'},
                    'body': json.dumps({'s3_uri': 's3://bucket/uploads/job/missing.jpg'})
                }
                response = module.handler(event, MockContext('process-handler'))

            # Handler returns 400 for validation errors or 500 for internal errors
            assert response['statusCode'] in [400, 500]
            body = json.loads(response['body'])
            assert 'error' in body
            # Error message should be descriptive
            assert len(body['error']) > 5

    def test_returns_descriptive_error_for_job_not_found(self):
        """Test descriptive error for job not found."""
        with patch('boto3.resource') as mock_boto_resource:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # No item
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            module = load_handler_module('status-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table'}):
                event = {
                    'headers': {'x-api-key': 'k'},
                    'pathParameters': {'job_id': 'nonexistent-job'}
                }
                response = module.handler(event, MockContext('status-handler'))

            assert response['statusCode'] == 404
            body = json.loads(response['body'])
            assert 'not found' in body['error'].lower()
