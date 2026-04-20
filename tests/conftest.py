"""
conftest.py — shared fixtures for Orion tests
"""
import sys
import os
import logging

# Suppress verbose logging during tests
logging.basicConfig(level=logging.WARNING)

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))