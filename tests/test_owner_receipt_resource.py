"""Real finite-lease receipt checks; no database or driver imports."""
import hashlib
import io
import os
import zipfile
from pathlib import Path

import pytest

from modkit_events.persistence import _resource_io as rio
from modkit_events.persistence import migrations as m

SQL = Path(m.__file__).parent / "sql"


def available():
    assert callable(getattr(m, "read_owner_receipt", None)), "missing receipt API"
    return m.manifest()[0]


def test_real_owned_receipt_and_six_native_binds():
    migration = available()
    result = m.read_owner_receipt(migration)
    raw = (SQL / "owner_receipt.sql").read_bytes()
    assert result.encode() == raw
    assert hashlib.sha256(raw).hexdigest() == m._OWNER_RECEIPT_SHA256
    for n in range(1, 7):
        assert result.count("$" + str(n)) == 1
    assert "$7" not in result and "pg_catalog.clock_timestamp()" in result
    assert "ON CONFLICT" not in result and "COMMIT" not in result
    assert len(raw) <= 4096
    assert "read_owner_receipt" in m.__all__


@pytest.fixture
def owned(tmp_path, monkeypatch):
    available()
    for name in ("manifest.json", "0001_initial.sql", "grants_runtime.sql", "owner_receipt.sql"):
        (tmp_path / name).write_bytes((SQL / name).read_bytes())
    monkeypatch.setattr(rio, "open_lease", lambda anchor: rio.PosixLease(tmp_path))
    return tmp_path


@pytest.mark.parametrize("mode", ["missing", "tampered", "oversize", "directory", "symlink"])
def test_bad_receipt_fails_closed(owned, mode):
    migration = m.manifest()[0]
    leaf = owned / "owner_receipt.sql"
    leaf.unlink()
    if mode == "tampered":
        leaf.write_bytes(b"SELECT 1;")
    elif mode == "oversize":
        leaf.write_bytes(b"x" * 4097)
    elif mode == "directory":
        leaf.mkdir()
    elif mode == "symlink":
        leaf.symlink_to(owned / "0001_initial.sql")
    with pytest.raises((ValueError, OSError)):
        m.read_owner_receipt(migration)


def test_invalid_utf8_rejected_after_digest_check(owned, monkeypatch):
    migration = m.manifest()[0]
    raw = b"\xff"
    (owned / "owner_receipt.sql").write_bytes(raw)
    monkeypatch.setattr(m, "_OWNER_RECEIPT_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="encoding"):
        m.read_owner_receipt(migration)


@pytest.mark.parametrize("bad", [None, object(), {}, "events"])
def test_wrong_descriptor_type_rejected_before_io(monkeypatch, bad):
    available()
    def forbidden(*args):
        raise AssertionError("invalid descriptor reached I/O")
    monkeypatch.setattr(rio, "open_lease", forbidden)
    with pytest.raises(ValueError):
        m.read_owner_receipt(bad)


def test_forged_same_shape_and_subclass_rejected(owned):
    migration = m.manifest()[0]
    forged = object.__new__(m.Migration)
    for field in migration.__slots__:
        object.__setattr__(forged, field, getattr(migration, field))
    object.__setattr__(forged, "version", 2)
    with pytest.raises(ValueError):
        m.read_owner_receipt(forged)
    class Derived(m.Migration):
        pass
    values = {f: getattr(migration, f) for f in migration.__slots__}
    with pytest.raises(ValueError):
        m.read_owner_receipt(Derived(**values))


def test_valid_but_not_member_descriptor_rejected(owned):
    migration = m.manifest()[0]
    resources = tuple(m.SQLResource(path=x.path, sha256="a"*64) for x in migration.resources)
    changed = m.Migration(component="events", version=1, resources=resources,
        migration_digest=m._aggregate(resources), depends_on=(),
        catalog_contract_id="modkit-pg-ab-2", scope_format_id="MKSC-1", intent_format_id="MKPF-1")
    with pytest.raises(ValueError):
        m.read_owner_receipt(changed)


def test_mutated_migration_resource_fails_before_receipt(owned):
    migration = m.manifest()[0]
    (owned / "grants_runtime.sql").write_bytes(b"SELECT 1;")
    with pytest.raises(ValueError, match="digest"):
        m.read_owner_receipt(migration)


@pytest.mark.parametrize("limit", [None, 8192, 4096, 100])
def test_receipt_bound_cannot_be_widened_posix(tmp_path, limit):
    (tmp_path / "owner_receipt.sql").write_bytes(b"x"*4097)
    with rio.PosixLease(tmp_path) as lease:
        with pytest.raises(ValueError, match="large"):
            lease.read("owner_receipt.sql", limit)


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_zip_receipt_identity_and_bound(compression):
    available()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr("pkg/owner_receipt.sql", b"x"*4097)
    with rio.ZipLease(stream.getvalue(), "pkg/") as lease:
        with pytest.raises(ValueError, match="large"):
            lease.read("owner_receipt.sql", 100000)
    stream = io.BytesIO()
    raw = (SQL / "owner_receipt.sql").read_bytes()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr("pkg/owner_receipt.sql", raw)
    with rio.ZipLease(stream.getvalue(), "pkg/") as lease:
        assert lease.read("owner_receipt.sql") == raw


def test_unknown_origin_fails_closed(monkeypatch):
    migration = available()
    from modkit_events.persistence import sql
    monkeypatch.setattr(sql, "__loader__", object())
    with pytest.raises(ValueError, match="backend"):
        m.read_owner_receipt(migration)


def test_close_uncertainty_never_returns_sql(owned, monkeypatch):
    migration = m.manifest()[0]
    close = os.close
    def close_then_fail(fd):
        close(fd)
        raise OSError("uncertain close")
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(OSError, match="uncertain close"):
        m.read_owner_receipt(migration)


def test_invalid_explicit_limits():
    available()
    for value in (-1, True, "4096"):
        with pytest.raises(ValueError):
            rio._limit("owner_receipt.sql", value)


def test_api_is_inert_until_called(monkeypatch):
    import importlib
    available()
    def forbidden(*args):
        raise AssertionError("import performs resource I/O")
    monkeypatch.setattr(rio, "open_lease", forbidden)
    importlib.reload(m)

def test_wrong_component_rejected_before_open(monkeypatch):
    migration = available()
    resources = tuple(m.SQLResource(path=x.path.replace("events/", "workers/"), sha256=x.sha256)
                      for x in migration.resources)
    other = m.Migration(component="workers", version=1, resources=resources,
        migration_digest=m._aggregate(resources),
        depends_on=(m.MigrationDependency(component="events", version=1,
                    migration_digest=migration.migration_digest),),
        catalog_contract_id="modkit-pg-ab-2", scope_format_id="MKSC-1", intent_format_id="MKPF-1")
    def forbidden(*args):
        raise AssertionError("wrong component reached I/O")
    monkeypatch.setattr(rio, "open_lease", forbidden)
    with pytest.raises(ValueError):
        m.read_owner_receipt(other)


@pytest.mark.parametrize("target", ["manifest.json", "0001_initial.sql", "grants_runtime.sql"])
def test_missing_dependency_never_returns_receipt(owned, target):
    migration = m.manifest()[0]
    (owned / target).unlink()
    with pytest.raises((ValueError, OSError)):
        m.read_owner_receipt(migration)


def test_receipt_archive_full_api_and_corruption(monkeypatch):
    migration = available()
    raw_receipt = (SQL / "owner_receipt.sql").read_bytes()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in ("manifest.json", "0001_initial.sql", "grants_runtime.sql", "owner_receipt.sql"):
            archive.writestr("pkg/" + name, (SQL / name).read_bytes())
    raw = stream.getvalue()
    monkeypatch.setattr(rio, "open_lease", lambda anchor: rio.ZipLease(raw, "pkg/"))
    assert m.read_owner_receipt(migration).encode() == raw_receipt
    offset = raw.index(raw_receipt)
    damaged = bytearray(raw)
    damaged[offset] ^= 1
    monkeypatch.setattr(rio, "open_lease", lambda anchor: rio.ZipLease(bytes(damaged), "pkg/"))
    with pytest.raises(ValueError):
        m.read_owner_receipt(migration)
    monkeypatch.setattr(rio, "open_lease", lambda anchor: rio.ZipLease(raw[:-10], "pkg/"))
    with pytest.raises(ValueError):
        m.read_owner_receipt(migration)


@pytest.mark.parametrize("name", ["../owner_receipt.sql", "/owner_receipt.sql",
                                  "x/owner_receipt.sql", "OWNER_RECEIPT.sql"])
def test_receipt_path_aliases_denied(name):
    available()
    with pytest.raises(ValueError, match="containment"):
        rio._limit(name, None)
