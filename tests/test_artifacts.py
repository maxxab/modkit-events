"""Negative checks for the installed-artifact gate itself."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_installation", Path(__file__).resolve().parents[1] / "scripts/check_installation.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_rejects_checkout_origin(tmp_path):
    with pytest.raises(AssertionError, match="outside"):
        checker.assert_installation(Path("/checkout/pkg/__init__.py"), tmp_path, "0.1", "0.1")


def test_rejects_metadata_mismatch(tmp_path):
    with pytest.raises(AssertionError, match="version"):
        checker.assert_installation(
            tmp_path / "site-packages/pkg/__init__.py", tmp_path, "0.2", "0.1"
        )


def test_accepts_matching_installation(tmp_path):
    checker.assert_installation(tmp_path / "site-packages/pkg/__init__.py", tmp_path, "0.1", "0.1")
