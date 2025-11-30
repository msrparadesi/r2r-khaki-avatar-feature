"""Integration tests for end-to-end agent workflow. Req: 4.1-4.5, 5.1-5.5, 7.1-7.5, 8.1-8.5"""
import json
import os
import sys
import uuid
import base64
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


class TestProcessWorker:
    """Tests for process worker Lambda. Requirements: 4.5, 11.1, 11.2, 11.4"""

    def test_processes_sqs_message_and_invokes_agent(self):
        """Test SQS message processing and agent invocation. Req: 4.5"""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            # Mock DynamoDB
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            # Mock S3 client
            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {'Body': MagicMock(read=lambda: b'fake-image-data')}
            mock_s3.put_object.return_value = {}

            # Mock Bedrock agent client
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_agent.return_value = {'completion': []}

            def client_factory(service):
                if service == 's3':
                    return mock_s3
                elif service == 'bedrock-agent-runtime':
                    return mock_bedrock
                elif service == 'sqs':
                    return MagicMock()
                elif service == 'cloudwatch':
                    return MagicMock()
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

            assert response['statusCode'] == 200
            # Verify DynamoDB was updated
            assert mock_table.update_item.called

    def test_updates_job_status_to_processing(self):
        """Test job status update to processing. Req: 4.5"""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {'Body': MagicMock(read=lambda: b'fake-image')}
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_agent.return_value = {'completion': []}

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
                module.handler(event, MockContext('process-worker'))

            # Verify status was updated to processing
            update_calls = mock_table.update_item.call_args_list
            assert len(update_calls) > 0
            # First call should set status to processing
            first_call = update_calls[0]
            expr_values = first_call.kwargs.get('ExpressionAttributeValues', {})
            assert ':status' in expr_values


    def test_stores_results_in_dynamodb(self):
        """Test results storage in DynamoDB. Req: 4.5"""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb

            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {'Body': MagicMock(read=lambda: b'fake-image')}
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_agent.return_value = {'completion': []}

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
                module.handler(event, MockContext('process-worker'))

            # Verify final update includes identity_package
            update_calls = mock_table.update_item.call_args_list
            assert len(update_calls) > 0
            # Last call should include completed status
            last_call = update_calls[-1]
            expr_values = last_call.kwargs.get('ExpressionAttributeValues', {})
            assert ':status' in expr_values
            assert expr_values[':status'] == 'completed'

    def test_handles_missing_job_id_gracefully(self):
        """Test handling of invalid SQS messages. Req: 11.2"""
        with patch('boto3.resource') as mock_boto_resource, \
             patch('boto3.client') as mock_boto_client:
            mock_table = MagicMock()
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            mock_boto_client.return_value = MagicMock()

            module = load_handler_module('process-worker')
            with patch.dict(os.environ, {
                'DYNAMODB_TABLE_NAME': 'test-table',
                'S3_UPLOAD_BUCKET': 'test-upload-bucket',
                'S3_GENERATED_BUCKET': 'test-generated-bucket',
                'AGENT_RUNTIME_ARN': 'arn:aws:bedrock-agentcore:us-east-1:123:runtime/test-agent'
            }):
                # Missing job_id in message
                event = {
                    'Records': [{
                        'body': json.dumps({'s3_upload_key': 'uploads/test/image.jpg'})
                    }]
                }
                response = module.handler(event, MockContext('process-worker'))

            # Should complete without error but not process
            assert response['statusCode'] == 200
            mock_table.update_item.assert_not_called()
