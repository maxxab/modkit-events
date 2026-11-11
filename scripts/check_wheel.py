"""Install built artifacts into fresh environments outside the checkout."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import venv
import xml.etree.ElementTree as ET
from pathlib import Path

from release_verify import audit

# These test modules exercise imported package behavior with no checkout source.
# Full source/native/SQL/tooling tests remain mandatory in the separate CI lane.
BASE_TESTS = (
    "test_core.py",
    "test_consumer.py",
    "test_outbox.py",
    "test_isolation.py",
    "test_contracts.py",
    "test_contracts_compatibility.py",
    "test_contracts_delivery.py",
    "test_contracts_exports.py",
    "test_contracts_subscriptions.py",
    "test_batch_publication.py",
    "test_persistence_contracts.py",
    "test_persistence_boundaries.py",
    "test_catalog_contract.py",
    "test_native_binary_transport.py",
    "test_resource_cleanup_failure.py",
)
ADAPTER_TESTS = (
    "test_contracts_pydantic.py",
    "test_sqlalchemy.py",
    "test_redis_boundaries.py",
    "test_legacy_failure_reporting.py",
)


def stage_tests(root: Path, temp: Path, *, extras: bool, require_redis: bool):
    tests = temp / "tests"
    tests.mkdir(parents=True)
    selected = BASE_TESTS + (ADAPTER_TESTS if extras else ())
    if extras and require_redis:
        selected += ("test_redis.py",)
    for name in selected:
        shutil.copyfile(root / "tests" / name, tests / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--require-redis", action="store_true")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    root = Path(__file__).resolve().parents[1]
    match = re.fullmatch(r"modkit_events-([0-9]+\.[0-9]+\.[0-9]+)-py3-none-any\.whl", wheel.name)
    if match is None:
        raise ValueError("unexpected wheel filename")
    version = match[1]
    if args.require_redis and not os.environ.get("MODKIT_REDIS_URL"):
        raise ValueError("explicit disposable MODKIT_REDIS_URL required")
    audit(wheel, "modkit-events", version)
    for extras in (False, True):
        with tempfile.TemporaryDirectory(prefix="modkit-events-wheel-") as directory:
            temp = Path(directory)
            venv.EnvBuilder(with_pip=True).create(temp / "venv")
            python = temp / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("PYTHON", "PYTEST_", "MODKIT_"))
            }
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONNOUSERSITE"] = "1"
            if args.require_redis:
                env["MODKIT_REQUIRE_REDIS"] = "1"
                env["MODKIT_REDIS_URL"] = os.environ["MODKIT_REDIS_URL"]

            def run(*command):
                subprocess.run([str(python), "-I", "-B", *command], cwd=temp, env=env, check=True)

            target = str(wheel) + ("[redis,sqlalchemy,pydantic]" if extras else "")
            run(
                "-m",
                "pip",
                "install",
                target,
                "pytest==9.2.0",
                "pytest-asyncio==1.4.1",
                *(["aiosqlite==0.22.1"] if extras else []),
            )
            stage_tests(root, temp, extras=extras, require_redis=args.require_redis)
            shutil.copy(root / "examples/sample_app.py", temp / "sample_app.py")
            (temp / "pytest.ini").write_text(
                "[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n"
            )
            (temp / "scripts").mkdir()
            shutil.copyfile(
                root / "scripts/check_installation.py", temp / "scripts/check_installation.py"
            )
            run("scripts/check_installation.py", version)
            if not extras:
                run(
                    "-c",
                    "import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('redis','sqlalchemy','pydantic'))",
                )
            run("-m", "pip", "check")
            run("sample_app.py")
            run(
                "-m",
                "pytest",
                "-p",
                "pytest_asyncio.plugin",
                "-q",
                "tests",
                "--junitxml=installed.xml",
            )
            suites = list(ET.parse(temp / "installed.xml").getroot().iter("testsuite"))
            if (
                not suites
                or sum(int(x.get("tests", "0")) for x in suites) == 0
                or any(
                    int(x.get(key, "0"))
                    for x in suites
                    for key in ("errors", "failures", "skipped")
                )
            ):
                raise ValueError("installed test lane incomplete")
    print("Installed base/adapter behavior verified; source/native tests remain separate gates")


if __name__ == "__main__":
    main()
