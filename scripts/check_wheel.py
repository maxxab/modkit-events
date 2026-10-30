"""Install built artifacts into fresh environments outside the checkout."""

import argparse
import os
import shutil
import subprocess
import tempfile
import venv
import zipfile
from email.parser import Parser
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--require-redis", action="store_true")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        version = Parser().parsestr(archive.read(metadata).decode())["Version"]
        assert not any("development-standards" in name or "AGENTS" in name for name in names)
        for name in names:
            content = archive.read(name)
            assert not any(
                marker in content for marker in (b"/workspace/", b"operations_erp", b"/home/")
            ), name
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

            target = str(wheel) + ("[redis,sqlalchemy]" if extras else "")
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
                }:
                    continue
                shutil.copy(test, temp / "tests" / test.name)
            shutil.copy(root / "examples/sample_app.py", temp / "sample_app.py")
            (temp / "pytest.ini").write_text(
                "[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n"
            )
            shutil.copytree(root / "scripts", temp / "scripts")
            run("scripts/check_installation.py", version)
            if not extras:
                run(
                    "-c",
                    "import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('redis','sqlalchemy'))",
                )
            run("-m", "pip", "check")
            run("sample_app.py")
            run("-m", "pytest", "-q", "tests")
    print("Installed wheel base/extras verified; Redis requires explicit service environment")


if __name__ == "__main__":
    main()
