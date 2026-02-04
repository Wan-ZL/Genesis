"""Pytest configuration and fixtures."""
import os
import importlib

# Disable authentication globally BEFORE any imports
# This must happen at module load time
os.environ["ASSISTANT_AUTH_ENABLED"] = "false"
