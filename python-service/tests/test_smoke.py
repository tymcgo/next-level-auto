"""Basic smoke tests for python-service."""

import importlib
import os
import sys

import pytest

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _try_import(module_name: str):
    """Try to import a module, skip if dependencies are missing."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        pytest.skip(f"Missing dependency for {module_name}: {e}")


def test_import_main():
    """Main module should import without error."""
    mod = _try_import("main")
    assert mod is not None


def test_import_planner():
    """Planner module should import without error."""
    mod = _try_import("agent.planner")
    assert mod is not None


def test_import_governance_engine():
    """Governance engine module should import without error."""
    mod = _try_import("governance.governance_engine")
    assert mod is not None


def test_import_tool_registry():
    """Tool registry module should import without error."""
    mod = _try_import("tools.tool_registry")
    assert mod is not None


def test_python_version():
    """Python version should be 3.11+."""
    assert sys.version_info >= (3, 11)
