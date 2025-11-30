"""Integration tests for S3 event-triggered flow. Req: 2.1, 2.2, 2.3, 2.4, 2.5"""
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


class TestS3EventHandler:
    """Tests for S3 event handler. Requirements: 2.1-2.5"""

    def test_processes_valid_s3_event(self):
        """Test processing valid S3 upload event. Req: 2.1, 2.3, 2.4"""
        with patch('boto3.resource') as mock_boto_resource, patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # No existing item
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_sqs = MagicMock()
            mock_boto_client.return_value = mock_sqs

            module = load_handler_module('s3-event-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'Records': [{
                        's3': {
                            'bucket': {'name': 'petavatar-uploads'},
                            'object': {'key': 'uploads/test-job-id/image.jpg'}
                        }
                    }]
                }
                response = module.handler(event, MockContext('s3-event-handler'))

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['processed'] == 1
            assert body['errors'] == 0
            mock_table.put_item.assert_called_once()
            mock_sqs.send_message.assert_called_once()

    def test_validates_object_key_pattern(self):
        """Test object key pattern validation. Req: 2.2"""
        with patch('boto3.resource') as mock_boto_resource, patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_sqs = MagicMock()
            mock_boto_client.return_value = mock_sqs

            module = load_handler_module('s3-event-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                # Invalid key pattern - not in uploads/{job_id}/* format
                event = {
                    'Records': [{
                        's3': {
                            'bucket': {'name': 'petavatar-uploads'},
                            'object': {'key': 'invalid/path/image.jpg'}
                        }
                    }]
                }
                response = module.handler(event, MockContext('s3-event-handler'))

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['processed'] == 0
            assert body['errors'] == 1
            mock_table.put_item.assert_not_called()
            mock_sqs.send_message.assert_not_called()

    def test_creates_dynamodb_record_if_not_exists(self):
        """Test DynamoDB record creation. Req: 2.3"""
        with patch('boto3.resource') as mock_boto_resource, patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # No existing item
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_sqs = MagicMock()
            mock_boto_client.return_value = mock_sqs

            module = load_handler_module('s3-event-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'Records': [{
                        's3': {
                            'bucket': {'name': 'petavatar-uploads'},
                            'object': {'key': 'uploads/new-job-id/image.jpg'}
                        }
                    }]
                }
                module.handler(event, MockContext('s3-event-handler'))

            # Verify put_item was called with correct job_id and status
            mock_table.put_item.assert_called_once()
            call_args = mock_table.put_item.call_args
            item = call_args.kwargs.get('Item', {})
            assert item['job_id'] == 'new-job-id'
            assert item['status'] == 'queued'


    def test_sends_message_to_processing_queue(self):
        """Test SQS message sending. Req: 2.4"""
        with patch('boto3.resource') as mock_boto_resource, patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_sqs = MagicMock()
            mock_boto_client.return_value = mock_sqs

            module = load_handler_module('s3-event-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                event = {
                    'Records': [{
                        's3': {
                            'bucket': {'name': 'petavatar-uploads'},
                            'object': {'key': 'uploads/job-123/image.jpg'}
                        }
                    }]
                }
                module.handler(event, MockContext('s3-event-handler'))

            mock_sqs.send_message.assert_called_once()
            call_args = mock_sqs.send_message.call_args
            message_body = json.loads(call_args.kwargs.get('MessageBody', '{}'))
            assert message_body['job_id'] == 'job-123'
            assert message_body['s3_upload_key'] == 'uploads/job-123/image.jpg'

    def test_logs_invalid_events_without_failing(self):
        """Test invalid event handling. Req: 2.5"""
        with patch('boto3.resource') as mock_boto_resource, patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_sqs = MagicMock()
            mock_boto_client.return_value = mock_sqs

            module = load_handler_module('s3-event-handler')
            with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'SQS_QUEUE_URL': 'https://sqs/q'}):
                # Mix of valid and invalid events
                event = {
                    'Records': [
                        {'s3': {'bucket': {'name': 'b'}, 'object': {'key': 'invalid/key'}}},
                        {'s3': {'bucket': {'name': 'b'}, 'object': {'key': 'uploads/valid-job/img.jpg'}}}
                    ]
                }
                mock_table.get_item.return_value = {}
                response = module.handler(event, MockContext('s3-event-handler'))

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['processed'] == 1
            assert body['errors'] == 1
