"""Verify release identity, immutable artifact hashes, and installed distributions."""

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import zipfile
import zlib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import IO, Any, cast

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


# Deliberate finite Events publication limits, not an archive expansion budget.
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 512
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_TAR_BYTES = 20 * 1024 * 1024


def inflate_exact(data: bytes, limit: int, *, gzip_stream: bool = False) -> bytes:
    decoder = zlib.decompressobj(-15)
    try:
        result = decoder.decompress(data, limit + 1)
    except zlib.error as error:
        raise ValueError("invalid deflate stream") from error
    require(
        len(result) <= limit, "tar decompressed size limit" if gzip_stream else "member size limit"
    )
    require(decoder.eof and not decoder.unconsumed_tail, "incomplete deflate stream")
    if gzip_stream:
        require(len(decoder.unused_data) == 8, "invalid gzip footer/trailing data")
        crc, size = struct.unpack("<2I", decoder.unused_data)
        require(size == len(result) and crc == zlib.crc32(result), "gzip size/CRC mismatch")
    else:
        require(not decoder.unused_data, "trailing deflate data")
    return result


def physical_zip(data: bytes) -> tuple[dict[str, bytes], list[str]]:
    require(len(data) >= 22, "invalid ZIP footer")
    signature, disk, cd_disk, disk_count, count, cd_size, cd_start, comment = struct.unpack(
        "<4s4H2IH", data[-22:]
    )
    require(signature == b"PK\x05\x06" and comment == 0, "invalid ZIP footer/comment")
    require(disk == cd_disk == 0 and disk_count == count, "multidisk ZIP")
    require(count <= MAX_MEMBERS, "artifact member count limit")
    require(cd_size <= 512 * 1024, "ZIP directory size limit")
    require(cd_start + cd_size == len(data) - 22, "invalid ZIP directory extent")
    records: list[tuple[int, bytes, tuple[int, ...], str, bool]] = []
    offset = cd_start
    sizes = []
    while offset < len(data) - 22:
        require(len(records) < MAX_MEMBERS, "artifact member count limit")
        require(offset + 46 <= len(data) - 22, "truncated ZIP central header")
        fields = struct.unpack_from("<4s6H3I5H2I", data, offset)
        (
            sig,
            made,
            needed,
            flags,
            method,
            time,
            date,
            crc,
            packed,
            size,
            name_len,
            extra_len,
            comment_len,
            start_disk,
            internal,
            external,
            local,
        ) = fields
        require(sig == b"PK\x01\x02", "invalid ZIP central header")
        require(extra_len == comment_len == start_disk == internal == 0, "unsupported ZIP metadata")
        require(made in (20, 0x314) and needed == 20, "unsupported ZIP version")
        require(flags in (0, 0x800) and method in (0, 8), "unsupported ZIP flags/method")
        end = offset + 46 + name_len
        require(end <= len(data) - 22, "truncated ZIP name")
        raw_name = data[offset + 46 : end]
        try:
            name = raw_name.decode("utf-8" if flags & 0x800 else "ascii")
        except UnicodeError as error:
            raise ValueError("unsupported ZIP name encoding") from error
        safe_name(name)
        directory = name.endswith("/")
        mode = external >> 16
        require(not stat.S_ISLNK(mode), "ZIP symlink")
        require(
            stat.S_IFMT(mode) in (0, stat.S_IFDIR if directory else stat.S_IFREG), "ZIP member type"
        )
        require(external & 0xFFFF in (0, 0x10 if directory else 0), "unsupported ZIP attributes")
        sizes.append((name, size, directory))
        member_sizes(sizes)
        records.append((local, raw_name, fields[2:10], name, directory))
        offset = end
    require(offset == cd_start + cd_size and len(records) == count, "ZIP directory count mismatch")
    audit_names([(r[3], r[4]) for r in records])
    files: dict[str, bytes] = {}
    directories: list[str] = []
    cursor = 0
    for local, raw_name, central, name, directory in sorted(records):
        require(local == cursor and local + 30 <= cd_start, "ZIP local interval mismatch")
        fields = struct.unpack_from("<4s5H3I2H", data, local)
        require(fields[0] == b"PK\x03\x04" and fields[1:9] == central, "ZIP local/central mismatch")
        name_len, extra_len = fields[9:11]
        require(name_len == len(raw_name) and extra_len == 0, "unsupported ZIP local metadata")
        start = local + 30 + name_len
        require(data[local + 30 : start] == raw_name, "ZIP local name mismatch")
        _, _, method, _, _, crc, packed, size = central
        cursor = start + packed
        require(cursor <= cd_start, "ZIP payload interval mismatch")
        if method == 0:
            require(packed == size, "stored ZIP size mismatch")
            content = data[start:cursor]
        else:
            content = inflate_exact(data[start:cursor], size)
        require(len(content) == size and zlib.crc32(content) == crc, "ZIP size/CRC mismatch")
        if directory:
            directories.append(name)
        else:
            files[name] = content
    require(cursor == cd_start, "ZIP unreferenced bytes")
    return files, directories


def tar_number(raw: bytes) -> int:
    require(re.fullmatch(rb"[0-7]+[\x00 ]*", raw), "unsupported tar numeric field")
    return int(raw.rstrip(b"\0 "), 8)


def tar_text(raw: bytes) -> str:
    value, separator, padding = raw.partition(b"\0")
    require(not separator or not any(padding), "noncanonical tar string padding")
    try:
        return value.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("invalid tar text") from error


def pax_fields(payload: bytes, remaining_keys: int) -> dict[str, str]:
    from artifact_policy import audit_content

    result: dict[str, str] = {}
    offset = 0
    while offset < len(payload):
        require(len(result) < min(8, remaining_keys), "PAX key count limit")
        space = payload.find(b" ", offset, offset + 12)
        require(space > offset and payload[offset:space].isdigit(), "invalid PAX length")
        length = int(payload[offset:space])
        require(str(length).encode() == payload[offset:space], "noncanonical PAX length")
        end = offset + length
        require(
            space + 1 < end <= len(payload) and payload[end - 1 : end] == b"\n",
            "invalid PAX record",
        )
        key, separator, value = payload[space + 1 : end - 1].partition(b"=")
        require(separator and key in (b"path", b"mtime"), "unsupported PAX key")
        name = key.decode("ascii")
        require(name not in result, "duplicate PAX key")
        audit_content("PAX metadata", value)
        try:
            text = value.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("invalid PAX text") from error
        if name == "path":
            safe_name(text)
        else:
            require(
                re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,9})?", text), "unsupported PAX timestamp"
            )
        result[name] = text
        offset = end
    return result


def physical_tar(data: bytes) -> tuple[dict[str, bytes], list[str]]:
    from artifact_policy import audit_content

    require(len(data) >= 18 and data[:3] == b"\x1f\x8b\x08", "invalid gzip header")
    require(
        data[3] == 0 and data[8] in (0, 2, 4) and data[9] in (3, 255), "unsupported gzip metadata"
    )
    raw = inflate_exact(data[10:], MAX_TAR_BYTES, gzip_stream=True)
    require(len(raw) % 512 == 0, "invalid tar framing")
    offset = count = metadata_bytes = keys = 0
    pending: dict[str, str] | None = None
    files: dict[str, bytes] = {}
    directories: list[str] = []
    sizes = []
    entries: list[tuple[str, bool]] = []
    while offset + 512 <= len(raw):
        header = raw[offset : offset + 512]
        if not any(header):
            require(len(raw) - offset >= 1024 and not any(raw[offset:]), "invalid tar end padding")
            require(pending is None, "orphan PAX header")
            audit_names(entries)
            return files, directories
        count += 1
        require(count <= MAX_MEMBERS, "artifact physical header count limit")
        checksum = tar_number(header[148:156])
        require(checksum == sum(header[:148]) + 256 + sum(header[156:]), "tar checksum mismatch")
        require(
            header[257:265] == b"ustar\x0000" and not any(header[500:]), "unsupported tar header"
        )
        kind = header[156:157]
        require(kind in (b"0", b"\0", b"5", b"x"), "nonregular tar member")
        name = tar_text(header[:100])
        prefix = tar_text(header[345:500])
        name = prefix + "/" + name if prefix else name
        if kind != b"x" or name != "././@PaxHeader":
            safe_name(name)
        audit_content("tar name", name.encode())
        require(
            not any(header[157:257]) and not any(header[265:329]),
            "unsupported tar owner/link metadata",
        )
        require(
            tar_number(header[108:116]) == tar_number(header[116:124]) == 0, "unsupported tar owner"
        )
        tar_number(header[100:108])
        tar_number(header[136:148])
        require(all(b in (0, 48) for b in header[329:345]), "unsupported tar device metadata")
        size = tar_number(header[124:136])
        if kind == b"x":
            require(pending is None, "PAX extension chain")
            require(size <= MAX_METADATA_BYTES, "tar header read size limit")
            metadata_bytes += size
            require(metadata_bytes <= MAX_METADATA_BYTES, "PAX cumulative metadata limit")
        else:
            if pending is not None:
                require(kind in (b"0", b"\0"), "PAX requires regular member")
                name = pending.get("path", name)
            sizes.append((name, size, kind == b"5"))
            member_sizes(sizes)
        start = offset + 512
        end = start + size
        offset = start + ((size + 511) // 512) * 512
        require(offset <= len(raw), "truncated tar payload")
        require(not any(raw[end:offset]), "nonzero tar payload padding")
        if kind == b"x":
            pending = pax_fields(raw[start:end], 64 - keys)
            keys += len(pending)
            require(keys <= 64, "PAX cumulative key limit")
            continue
        entries.append((name, kind == b"5"))
        require(name not in files and name not in directories, "duplicate tar entries")
        if kind == b"5":
            directories.append(name.rstrip("/"))
        else:
            files[name] = raw[start:end]
        pending = None
    raise ValueError("missing tar end padding")


def bounded_archive(
    path: Path, wheel: bool, version: str
) -> tuple[dict[str, bytes], list[str], bytes]:
    with path.open("rb") as source:
        data = source.read(MAX_ARCHIVE_BYTES + 1)
    require(len(data) <= MAX_ARCHIVE_BYTES, "archive size limit")
    files, directories = physical_zip(data) if wheel else physical_tar(data)
    if wheel:
        metas = [name for name in files if name.endswith(".dist-info/METADATA")]
        require(
            metas == ["modkit_events-" + version + ".dist-info/METADATA"],
            "unexpected wheel metadata path",
        )
    else:
        roots = {name.split("/")[0] for name in [*files, *directories]}
        require(roots == {"modkit_events-" + version}, "unexpected sdist root")
        metas = [name for name in files if name.count("/") == 1 and name.endswith("/PKG-INFO")]
        require(len(metas) == 1, "ambiguous sdist metadata")
    return files, directories, files[metas[0]]


def bounded_read(source: IO[bytes], size: int) -> bytes:
    # Size was checked before this call; read at most size+1 and require exact bytes.
    result = source.read(size + 1)
    require(len(result) == size, "archive member size mismatch")
    return result


def member_sizes(entries: list[tuple[str, int, bool]]) -> None:
    require(len(entries) <= MAX_MEMBERS, "artifact member count limit")
    total = 0
    for name, size, directory in entries:
        require(0 <= size <= MAX_MEMBER_BYTES, "artifact member size limit")
        require(not directory or size == 0, "directory member has content")
        if name.endswith((".dist-info/METADATA", "/PKG-INFO")):
            require(size <= MAX_METADATA_BYTES, "metadata size limit")
        total += size
        require(total <= MAX_TOTAL_BYTES, "artifact aggregate size limit")


def audit(path: Path, project: str, version: str) -> None:
    require(path.is_file() and not path.is_symlink(), "not a regular distribution")
    bounded = project == "modkit-events"
    if bounded:
        require(path.stat().st_size <= MAX_ARCHIVE_BYTES, "archive size limit")
    wheel = path.name.endswith(".whl")
    files: dict[str, bytes] = {}
    directories: list[str] = []
    if bounded:
        files, directories, metadata = bounded_archive(path, wheel, version)
    elif wheel:
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
            members = list(t)
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
            with reader:
                metadata = reader.read()
    parsed = BytesParser().parsebytes(metadata)
    require(
        parsed.get_all("Name") == [project] and parsed.get_all("Version") == [version],
        "distribution identity mismatch",
    )

    if project == "modkit-events":
        from artifact_policy import audit_members

        audit_members(files, directories, wheel=wheel, version=version, metadata=parsed)


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
