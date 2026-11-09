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


def test_sdist_excludes_only_internal_sql_candidate_reports():
    """Configuration guard; real backend privacy selection has separate build evidence."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    targets = config["tool"]["hatch"]["build"]["targets"]
    assert targets["sdist"].get("exclude") == ["/docs/sql-candidates/**/README.md"]
    assert targets["sdist"]["include"] == [
        "src",
        "tests",
        "examples",
        "scripts",
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "requirements-dev.txt",
    ]
    assert targets["wheel"] == {"packages": ["src/modkit_events"]}


def test_installed_lane_has_closed_base_tests_without_source_or_adapters(tmp_path, monkeypatch):
    """Installed smoke tests must collect with only base package and test tools."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    wheel_spec = importlib.util.spec_from_file_location(
        "wheel_checker", Path(__file__).resolve().parents[1] / "scripts/check_wheel.py"
    )
    wheel_checker = importlib.util.module_from_spec(wheel_spec)
    wheel_spec.loader.exec_module(wheel_checker)
    root = Path(__file__).resolve().parents[1]
    wheel_checker.stage_tests(root, tmp_path, extras=False, require_redis=False)
    staged = tmp_path / "tests"
    assert (staged / "test_contracts.py").is_file()
    assert (staged / "test_contracts_subscriptions.py").is_file()
    assert (staged / "test_contracts_delivery.py").is_file()
    assert not (tmp_path / "src").exists()
    assert not (staged / "test_legacy_failure_reporting.py").exists()
    assert not (staged / "test_native_recovery_issuer.py").exists()
    assert not (staged / "test_packaged_migrations.py").exists()
    assert not (staged / "test_redis.py").exists()
    # Missing required test source is fatal, never silently shrink coverage.
    with pytest.raises(FileNotFoundError):
        wheel_checker.stage_tests(
            tmp_path / "absent", tmp_path / "missing", extras=False, require_redis=False
        )


def test_installed_adapter_lane_requires_explicit_redis_service(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    wheel_spec = importlib.util.spec_from_file_location(
        "wheel_checker", Path(__file__).resolve().parents[1] / "scripts/check_wheel.py"
    )
    wheel_checker = importlib.util.module_from_spec(wheel_spec)
    wheel_spec.loader.exec_module(wheel_checker)
    root = Path(__file__).resolve().parents[1]
    ordinary, live = tmp_path / "ordinary", tmp_path / "live"
    wheel_checker.stage_tests(root, ordinary, extras=True, require_redis=False)
    wheel_checker.stage_tests(root, live, extras=True, require_redis=True)
    assert (ordinary / "tests/test_legacy_failure_reporting.py").is_file()
    assert (ordinary / "tests/test_sqlalchemy.py").is_file()
    assert not (ordinary / "tests/test_redis.py").exists()
    assert (live / "tests/test_redis.py").is_file()
