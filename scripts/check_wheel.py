"""Install built artifacts into fresh environments outside the checkout."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path

from release_verify import audit


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
    audit(wheel, "modkit-events", version)
    for extras in (False, True):
        with tempfile.TemporaryDirectory(prefix="modkit-events-wheel-") as directory:
            temp = Path(directory)
            venv.EnvBuilder(with_pip=True).create(temp / "venv")
            python = temp / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["PYTHONNOUSERSITE"] = "1"
            if args.require_redis:
                env["MODKIT_REQUIRE_REDIS"] = "1"

            def run(*command):
                subprocess.run([str(python), *command], cwd=temp, env=env, check=True)

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
            (temp / "tests").mkdir()
            for test in (root / "tests").glob("test_*.py"):
                if not extras and test.name in {
                    "test_redis.py",
                    "test_redis_boundaries.py",
                    "test_sqlalchemy.py",
                    "test_contracts_pydantic.py",
                }:
                    continue
                shutil.copy(test, temp / "tests" / test.name)
            shutil.copy(root / "examples/sample_app.py", temp / "sample_app.py")
            shutil.copy(root / "pyproject.toml", temp / "pyproject.toml")
            (temp / "pytest.ini").write_text(
                "[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n"
            )
            shutil.copytree(root / "scripts", temp / "scripts")
            run("scripts/check_installation.py", version)
            if not extras:
                run(
                    "-c",
                    "import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('redis','sqlalchemy','pydantic'))",
                )
            run("-m", "pip", "check")
            run("sample_app.py")
            run("-m", "pytest", "-q", "tests")
    print("Installed wheel base/extras verified; Redis requires explicit service environment")


if __name__ == "__main__":
    main()
