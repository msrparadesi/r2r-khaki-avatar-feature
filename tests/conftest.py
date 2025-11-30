"""
Pytest configuration and fixtures for PetAvatar tests.
"""
import os
import sys

# Add all handler directories to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'presigned-url-handler'))
sys.path.insert(0, os.path.join(project_root, 'process-handler'))
sys.path.insert(0, os.path.join(project_root, 'status-handler'))
sys.path.insert(0, os.path.join(project_root, 'result-handler'))
sys.path.insert(0, os.path.join(project_root, 's3-event-handler'))
sys.path.insert(0, os.path.join(project_root, 'process-worker'))
