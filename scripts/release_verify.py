"""Verify release identity, immutable artifact hashes, and installed distributions."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, cast

PROJECTS = {"modkit-api-responses", "modkit-api-versioning", "modkit-diagnostics", "modkit-events"}


def require(condition: object, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(project: str, version: str, sha: str, tag: str) -> None:
    require(project in PROJECTS, "unexpected project")
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "not a final semantic version")
    require(re.fullmatch(r"[a-f0-9]{40}", sha), "invalid source SHA")
    require(tag == "v" + version, "tag/version mismatch")


def safe_name(name: str) -> str:
    body = name[:-1] if name.endswith("/") else name
    parts = body.split("/")
    require(
        bool(body) and all(x not in {"", ".", ".."} for x in parts), "noncanonical archive path"
    )
    require(
        not any(x in name for x in '\\:<>"|?*') and not any(ord(x) < 32 for x in name),
        "unsafe portable archive path",
    )
    for part in parts:
        require(not part.endswith((".", " ")), "trailing-dot/space archive alias")
        require(
            not re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I),
            "reserved Windows path",
        )
    require(
        not any(x in {".git", ".env", "AGENTS.md", ".cursor", "__pycache__"} for x in parts),
        "private/unintended archive path",
    )
    return body


def audit_names(entries: list[tuple[str, bool]]) -> None:
    explicit = set()
    prefixes: dict[str, str] = {}
    kinds: dict[str, bool] = {}
    for name, is_directory in entries:
        body = safe_name(name)
        key = unicodedata.normalize("NFC", body).casefold()
        require(key not in explicit, "duplicate/portable alias archive path")
        explicit.add(key)
        parts = body.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            portable = unicodedata.normalize("NFC", prefix).casefold()
            require(
                portable not in prefixes or prefixes[portable] == prefix,
                "case/Unicode archive alias",
            )
            prefixes[portable] = prefix
            directory = index < len(parts) or is_directory
            require(
                portable not in kinds or kinds[portable] == directory,
                "file/directory archive collision",
            )
            kinds[portable] = directory


def audit(path: Path, project: str, version: str) -> None:
    require(path.is_file() and not path.is_symlink(), "not a regular distribution")
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            audit_names([(i.filename, i.is_dir()) for i in z.infolist()])
            require(len(names) == len(set(names)), "duplicate ZIP entries")
            for i in z.infolist():
                safe_name(i.filename)
                require(not stat.S_ISLNK(i.external_attr >> 16), "ZIP symlink")
            wheel_metas = [n for n in names if n.endswith(".dist-info/METADATA")]
            require(len(wheel_metas) == 1, "ambiguous wheel metadata")
            metadata = z.read(wheel_metas[0])
    else:
        with tarfile.open(path) as t:
            members = t.getmembers()
            audit_names([(i.name, i.isdir()) for i in members])
            require(len(members) == len({i.name for i in members}), "duplicate tar entries")
            for member in members:
                safe_name(member.name)
                require(member.isfile() or member.isdir(), "nonregular tar member")
            roots = {PurePosixPath(i.name).parts[0] for i in members}
            require(len(roots) == 1, "ambiguous sdist root")
            tar_metas = [
                member
                for member in members
                if member.isfile()
                and len(PurePosixPath(member.name).parts) == 2
                and member.name.endswith("/PKG-INFO")
            ]
            require(len(tar_metas) == 1, "ambiguous sdist metadata")
            reader = t.extractfile(tar_metas[0])
            if reader is None:
                raise ValueError("missing sdist metadata file")
            metadata = reader.read()
    parsed = BytesParser().parsebytes(metadata)
    require(
        parsed.get_all("Name") == [project] and parsed.get_all("Version") == [version],
        "distribution identity mismatch",
    )


def create(directory: Path, project: str, version: str, sha: str, tag: str) -> str:
    identity(project, version, sha, tag)
    stem = project.replace("-", "_") + "-" + version
    expected = {stem + "-py3-none-any.whl", stem + ".tar.gz"}
    require({p.name for p in directory.iterdir()} == expected, "unexpected build output set")
    files = {}
    for name in sorted(expected):
        p = directory / name
        audit(p, project, version)
        files[name] = {"sha256": digest(p), "size": p.stat().st_size}
    manifest = {
        "schema": 1,
        "project": project,
        "version": version,
        "source_sha": sha,
        "tag": tag,
        "files": files,
    }
    target = directory / "manifest.json"
    target.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return digest(target)


def verify(
    directory: Path, expected_digest: str, project: str, sha: str, tag: str
) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "missing/unsafe manifest")
    require(digest(manifest_path) == expected_digest, "manifest hash mismatch")
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    identity(project, manifest["version"], sha, tag)
    require(
        manifest["schema"] == 1
        and manifest["project"] == project
        and manifest["source_sha"] == sha
        and manifest["tag"] == tag,
        "manifest identity mismatch",
    )
    stem = project.replace("-", "_") + "-" + manifest["version"]
    require(
        set(manifest["files"]) == {stem + "-py3-none-any.whl", stem + ".tar.gz"},
        "manifest file set mismatch",
    )
    require(
        {p.name for p in directory.iterdir()} == set(manifest["files"]) | {"manifest.json"},
        "artifact file set mismatch",
    )
    for name, item in manifest["files"].items():
        p = directory / name
        require(p.is_file() and not p.is_symlink(), "unsafe artifact file")
        require(
            p.stat().st_size == item["size"] and digest(p) == item["sha256"],
            "artifact hash mismatch",
        )
        audit(p, project, manifest["version"])
    return manifest


def run(*args: object, **kwargs: Any) -> None:
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def check_wheel(root: Path, wheel: Path, project: str, redis: bool) -> None:
    command = [sys.executable, root / "scripts/check_wheel.py", wheel]
    if redis:
        command.append("--require-redis")
    if redis:
        result = subprocess.run(
            [str(x) for x in command], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        print(result.stdout)
        require(result.returncode == 0, "Redis installed-wheel checker failed")
        require(
            not re.search(r"\b[1-9][0-9]* skipped\b", result.stdout),
            "Redis installed-wheel tests skipped",
        )
    else:
        run(*command)
    if project == "modkit-api-versioning":
        run(*command, "--extras")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["create", "verify", "test"])
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest-sha")
    parser.add_argument("--redis", action="store_true")
    args = parser.parse_args()
    if args.mode == "create":
        config = tomllib.loads(Path("pyproject.toml").read_text())["project"]
        require(config["name"] == args.project, "source project mismatch")
        value = create(args.directory, args.project, config["version"], args.sha, args.tag)
        print(value)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("manifest_sha=" + value + "\n")
        return
    manifest = verify(args.directory, args.manifest_sha, args.project, args.sha, args.tag)
    if args.mode == "verify":
        return
    root = Path.cwd()
    wheel = next(args.directory.glob("*.whl")).resolve()
    if args.redis:
        require(
            args.project == "modkit-events"
            and os.environ.get("MODKIT_REQUIRE_REDIS") == "1"
            and os.environ.get("MODKIT_REDIS_URL"),
            "real Redis required",
        )
        # Existing tests fail instead of skipping when this environment is set.
        run(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_redis.py",
            "--junitxml=redis-source.xml",
        )
        import xml.etree.ElementTree as ET

        suites = ET.parse("redis-source.xml").getroot()
        require(
            sum(int(x.get("tests", "0")) for x in suites.iter("testsuite")) > 0,
            "no Redis tests collected",
        )
        require(
            sum(int(x.get("skipped", "0")) for x in suites.iter("testsuite")) == 0,
            "Redis source tests skipped",
        )
    check_wheel(root, wheel, args.project, args.redis)
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        with tarfile.open(next(args.directory.glob("*.tar.gz"))) as t:
            t.extractall(temp, filter="data")
        source = next(temp.iterdir())
        output = temp / "rebuilt"
        run(sys.executable, "-m", "build", "--wheel", "--outdir", output, source)
        rebuilt = next(output.glob("*.whl"))
        audit(rebuilt, args.project, manifest["version"])
        prefix = args.project.replace("-", "_") + "/"
        with zipfile.ZipFile(wheel) as a, zipfile.ZipFile(rebuilt) as b:
            require(
                {n: a.read(n) for n in a.namelist() if n.startswith(prefix)}
                == {n: b.read(n) for n in b.namelist() if n.startswith(prefix)},
                "sdist runtime differs from tested primary wheel",
            )
        check_wheel(source, rebuilt, args.project, args.redis)
    verify(args.directory, args.manifest_sha, args.project, args.sha, args.tag)


if __name__ == "__main__":
    main()
