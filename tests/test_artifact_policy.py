"""Exercise release privacy boundaries with inert, hand-authored archive fixtures."""

import gzip
import importlib.util
import io
import stat
import struct
import sys
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "release_verify_policy_test", SCRIPTS / "release_verify.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

# These are fixture expectations, deliberately independent of the production policy.
METADATA = b"""Metadata-Version: 2.4
Name: modkit-events
Version: 0.1.0
Requires-Python: >=3.12
Provides-Extra: pydantic
Provides-Extra: redis
Provides-Extra: sqlalchemy
Requires-Dist: pydantic<3,>=2.14; extra == 'pydantic'
Requires-Dist: redis<9,>=8.1; extra == 'redis'
Requires-Dist: SQLAlchemy[asyncio]<3,>=2.1.6; extra == 'sqlalchemy'

"""


# Independent test contract enumerated from reviewed source paths, not policy imports.
EXPECTED_RUNTIME = """
modkit_events/__init__.py
modkit_events/_failure_reporting.py
modkit_events/adapters/__init__.py
modkit_events/adapters/pydantic.py
modkit_events/adapters/redis.py
modkit_events/adapters/sqlalchemy.py
modkit_events/claims.py
modkit_events/codec.py
modkit_events/consumer.py
modkit_events/contracts.py
modkit_events/delivery.py
modkit_events/dispatch.py
modkit_events/models.py
modkit_events/outbox.py
modkit_events/persistence/__init__.py
modkit_events/persistence/_resource_io.py
modkit_events/persistence/bindings.py
modkit_events/persistence/catalog.py
modkit_events/persistence/errors.py
modkit_events/persistence/ledger.py
modkit_events/persistence/managed_lifecycle.py
modkit_events/persistence/migrations.py
modkit_events/persistence/models.py
modkit_events/persistence/native_codec.py
modkit_events/persistence/native_sync.py
modkit_events/persistence/observations.py
modkit_events/persistence/resource_lifecycle.py
modkit_events/persistence/resource_registry.py
modkit_events/persistence/rows.py
modkit_events/persistence/scope.py
modkit_events/persistence/sql/0001_initial.sql
modkit_events/persistence/sql/__init__.py
modkit_events/persistence/transitions.py
modkit_events/protocols.py
modkit_events/py.typed
modkit_events/retry.py
modkit_events/subscriptions.py
modkit_events/persistence/sql/manifest.json
modkit_events/persistence/sql/grants_runtime.sql
""".split()
EXPECTED_SUPPORT = """
examples/sample_app.py
scripts/artifact_policy.py
scripts/check_installation.py
scripts/check_wheel.py
scripts/release_verify.py
tests/sql_specs/binary_scope_vectors.sql
tests/sql_specs/canonical_j_vectors.sql
tests/sql_specs/chunk_frame_boundary_vectors.sql
tests/sql_specs/core_record_invariants.md
tests/sql_specs/decimal_binary64_vectors.sql
tests/sql_specs/dependent_records.md
tests/sql_specs/event_envelope_vectors.sql
tests/sql_specs/guard_constraint_schedules.md
tests/sql_specs/installation_profile_cases.md
tests/sql_specs/intent_literal_vectors.sql
tests/sql_specs/intent_projection_vectors.md
tests/sql_specs/json_replay_vectors.sql
tests/sql_specs/json_string_vectors.sql
tests/sql_specs/numeric_exact_boundary_vectors.sql
tests/sql_specs/opaque_evidence_bounds.md
tests/sql_specs/optional_instant_vectors.sql
tests/sql_specs/protected_material_vectors.sql
tests/sql_specs/segment10_event_readers.sql
tests/sql_specs/segment10_event_readers_schedules.md
tests/sql_specs/segment11_subscription_registration.sql
tests/sql_specs/segment11_subscription_registration_schedules.md
tests/sql_specs/segment12_inbox_admission.sql
tests/sql_specs/segment12_inbox_admission_schedules.md
tests/sql_specs/segment13_outbox_reader.sql
tests/sql_specs/segment14_outbox_enqueue.sql
tests/sql_specs/segment2_correction_stress.sql
tests/sql_specs/segment2_witness_index.sql
tests/sql_specs/segment3_attempt_history.sql
tests/sql_specs/segment3_operation_records.sql
tests/sql_specs/segment3_publication_records.sql
tests/sql_specs/segment3_record_oracles.md
tests/sql_specs/segment4_root_guard.sql
tests/sql_specs/segment4_root_guard_schedules.md
tests/sql_specs/segment5_arm_guard.sql
tests/sql_specs/segment5_arm_guard_schedules.md
tests/sql_specs/segment6_subtype_storage.sql
tests/sql_specs/segment6_subtype_storage_schedules.md
tests/sql_specs/segment7_complete_guard.sql
tests/sql_specs/segment7_complete_guard_schedules.md
tests/sql_specs/segment8_work_reader.sql
tests/sql_specs/segment9_readers.sql
tests/sql_specs/segment9_readers_schedules.md
tests/test_artifact_policy.py
tests/test_legacy_failure_reporting.py
tests/test_resource_cleanup_failure.py
tests/test_artifacts.py
tests/test_catalog_contract.py
tests/test_consumer.py
tests/test_contracts.py
tests/test_contracts_compatibility.py
tests/test_contracts_delivery.py
tests/test_contracts_exports.py
tests/test_contracts_pydantic.py
tests/test_contracts_subscriptions.py
tests/test_core.py
tests/test_isolation.py
tests/test_managed_lifecycle.py
tests/test_native_binary_transport.py
tests/test_native_sql_descriptor.py
tests/test_outbox.py
tests/test_persistence_contracts.py
tests/test_redis.py
tests/test_redis_boundaries.py
tests/test_resource_lifecycle.py
tests/test_scope_storage.py
tests/test_sqlalchemy.py
tests/test_standalone_package.py
tests/test_work_listing_sql.py
tests/test_audit_readers_sql.py
tests/test_publication_history_sql.py
tests/test_publication_claim_sql.py
tests/test_publication_renewal_sql.py
tests/test_publication_intent_sql.py
tests/test_publication_settlement_sql.py
pyproject.toml
README.md
LICENSE
CHANGELOG.md
requirements-dev.txt
""".split()


def fixture(kind):
    package = dict.fromkeys(EXPECTED_RUNTIME, b"# inert fixture\n") | {
        "modkit_events/__init__.py": b"# inert synthetic fixture\n",
        "modkit_events/py.typed": b"",
        "modkit_events/persistence/sql/__init__.py": b"",
        "modkit_events/persistence/sql/0001_initial.sql": b"-- synthetic only\n",
        "modkit_events/persistence/sql/manifest.json": b'{"synthetic": true}\n',
        "modkit_events/persistence/sql/grants_runtime.sql": b"-- synthetic only\n",
    }
    if kind == "wheel":
        return package | {
            "modkit_events-0.1.0.dist-info/METADATA": METADATA,
            "modkit_events-0.1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
            "modkit_events-0.1.0.dist-info/RECORD": b"",
            "modkit_events-0.1.0.dist-info/licenses/LICENSE": b"MIT\n",
        }
    return (
        dict.fromkeys(EXPECTED_SUPPORT, b"# inert fixture\n")
        | {"src/" + name: content for name, content in package.items()}
        | {
            "PKG-INFO": METADATA,
            "pyproject.toml": b"# synthetic fixture; never built\n",
            "README.md": b"Synthetic archive policy fixture\n",
            "LICENSE": b"MIT\n",
            "scripts/artifact_policy.py": b"# inert fixture\n",
            "scripts/release_verify.py": b"# inert fixture\n",
            "scripts/check_wheel.py": b"# inert fixture\n",
            "scripts/check_installation.py": b"# inert fixture\n",
        }
    )


@contextmanager
def clean_tar(target):
    with target.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as writer:
                yield writer


def raw_zip(files, *, changed=None, method=0, comment=b"", count=None):
    """Small independent physical ZIP fixture writer; permits deliberate lies."""
    changed = changed or {}
    body = bytearray()
    central = bytearray()
    for name, plain in files.items():
        options = changed.get(name, {})
        raw_name = options.get("name", name.encode())
        payload = options.get("payload", plain)
        encoded = payload if method == 0 else zlib.compress(payload)[2:-4]
        encoded = options.get("encoded", encoded)
        crc = zlib.crc32(options.get("crc_plain", payload))
        size = options.get("size", len(payload))
        extra = options.get("extra", b"")
        entry_comment = options.get("comment", b"")
        local = len(body)
        local_values = [20, 0, method, 0, 0, crc, len(encoded), size]
        for index, value in options.get("local", {}).items():
            local_values[index] = value
        local_extra = options.get("local_extra", extra)
        body += struct.pack(
            "<4s5H3I2H", b"PK\x03\x04", *local_values, len(raw_name), len(local_extra)
        )
        body += raw_name + local_extra + encoded
        central += struct.pack(
            "<4s6H3I5H2I",
            b"PK\x01\x02",
            20,
            20,
            0,
            method,
            0,
            0,
            crc,
            len(encoded),
            size,
            len(raw_name),
            len(extra),
            len(entry_comment),
            0,
            0,
            0,
            local,
        )
        central += raw_name + extra + entry_comment
    return bytes(
        body
        + central
        + struct.pack(
            "<4s4H2IH",
            b"PK\x05\x06",
            0,
            0,
            len(files) if count is None else count,
            len(files) if count is None else count,
            len(central),
            len(body),
            len(comment),
        )
        + comment
    )


def archive(directory, kind, files):
    stem = "modkit_events-0.1.0"
    target = directory / (stem + ("-py3-none-any.whl" if kind == "wheel" else ".tar.gz"))
    if kind == "wheel":
        with zipfile.ZipFile(target, "w") as writer:
            for name, content in files.items():
                writer.writestr(name, content)
    else:
        with clean_tar(target) as writer:
            for name, content in files.items():
                member = tarfile.TarInfo(stem + "/" + name)
                member.size = len(content)
                writer.addfile(member, io.BytesIO(content))
    return target


class ArtifactPolicyTests(unittest.TestCase):
    def audit(self, kind, files):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            path = archive(Path(temporary), kind, files)
            release.audit(path, "modkit-events", "0.1.0")

    def test_minimal_inert_policy_fixtures_are_accepted(self):
        for kind in ("wheel", "sdist"):
            with self.subTest(kind=kind):
                self.audit(kind, fixture(kind))

    def test_private_host_content_in_approved_member_is_rejected(self):
        for kind in ("wheel", "sdist"):
            for payload in (
                b"/" + b"home/alice/evidence",
                b"/" + b"workspace/private",
                b"/" + b"Users/alice/private",
                b"C:" + b"\\Users\\alice\\private",
            ):
                with self.subTest(kind=kind, payload=payload):
                    files = fixture(kind)
                    key = ("src/" if kind == "sdist" else "") + "modkit_events/__init__.py"
                    files[key] = payload
                    with self.assertRaisesRegex(ValueError, "private"):
                        self.audit(kind, files)

    def test_unreviewed_members_and_private_schedule_are_rejected(self):
        cases = (
            ("wheel", "modkit_events/secret.txt"),
            ("wheel", "other/__init__.py"),
            ("sdist", "docs/handoffs/session.md"),
            ("sdist", "tests/sql_specs/segment8_work_reader_schedules.md"),
            ("sdist", "scripts/unreviewed.py"),
        )
        for kind, member in cases:
            with self.subTest(kind=kind, member=member):
                with self.assertRaisesRegex(ValueError, "member"):
                    self.audit(kind, fixture(kind) | {member: b"public-looking text"})

    def test_typing_migration_resources_and_license_are_required(self):
        for kind in ("wheel", "sdist"):
            for suffix in (
                "py.typed",
                "0001_initial.sql",
                "manifest.json",
                "grants_runtime.sql",
                "LICENSE",
            ):
                with self.subTest(kind=kind, missing=suffix):
                    files = fixture(kind)
                    del files[next(name for name in files if name.endswith(suffix))]
                    with self.assertRaisesRegex(ValueError, "required"):
                        self.audit(kind, files)

    def test_dependency_and_extra_drift_is_rejected_in_both_metadata_formats(self):
        variants = (
            METADATA.replace(b"Provides-Extra: redis\n", b""),
            METADATA.replace(b"Provides-Extra: redis\n", b"Provides-Extra: native\n"),
            METADATA.replace(b"redis<9,>=8.1", b"redis>=8"),
            METADATA.replace(b"Requires-Dist: redis<9,>=8.1; extra == 'redis'\n", b""),
            METADATA.replace(b"; extra == 'redis'", b""),
            METADATA.replace(b"\n\n", b"\nRequires-Dist: surprise>=1\n\n"),
            METADATA.replace(b"\n\n", b"\nProvides-Extra: redis\n\n"),
            METADATA.replace(b"\n\n", b"\nRequires-Dist: redis<9,>=8.1; extra == 'redis'\n\n"),
        )
        for kind in ("wheel", "sdist"):
            for index, content in enumerate(variants):
                with self.subTest(kind=kind, variant=index):
                    files = fixture(kind)
                    key = next(name for name in files if name.endswith(("/METADATA", "PKG-INFO")))
                    files[key] = content
                    with self.assertRaisesRegex(ValueError, "dependency|extras"):
                        self.audit(kind, files)

    def test_equivalent_dependency_order_and_quotes_are_accepted(self):
        for kind in ("wheel", "sdist"):
            files = fixture(kind)
            key = next(name for name in files if name.endswith(("/METADATA", "PKG-INFO")))
            files[key] = METADATA.replace(
                b"SQLAlchemy[asyncio]<3,>=2.1.6", b"sqlalchemy[asyncio]>=2.1.6, <3"
            ).replace(b"'", b'"')
            self.audit(kind, files)

    def test_only_exact_isolation_negative_sentinel_is_accepted(self):
        sentinel = (
            b"        if fullname.split('.')[0] in {'redis', 'sqlalchemy', 'operations"
            b"_erp', 'modkit_diagnostics'}:\n"
        )
        for text in (sentinel,):
            self.audit("sdist", fixture("sdist") | {"tests/test_isolation.py": text})
        for text in (
            sentinel + b"import operations" + b"_erp\n",
            sentinel.rstrip() + b" # local reference\n",
            b"import operations" + b"_erp\n",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "private"):
                    self.audit("sdist", fixture("sdist") | {"tests/test_isolation.py": text})

    def test_sdist_requires_checker_sources_for_rebuilt_install_validation(self):
        for member in (
            "scripts/artifact_policy.py",
            "scripts/release_verify.py",
            "scripts/check_wheel.py",
            "scripts/check_installation.py",
        ):
            with self.subTest(missing=member):
                files = fixture("sdist")
                del files[member]
                with self.assertRaisesRegex(ValueError, "required"):
                    self.audit("sdist", files)

    def test_backend_forced_public_ignore_rules_are_accepted(self):
        self.audit(
            "sdist", fixture("sdist") | {".gitignore": b".development" + b"-standards/POLICY.md\n"}
        )

    def test_sdist_explicit_root_and_package_directories_are_accepted(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "fixture.tar.gz"
            with clean_tar(target) as writer:
                for name in ("modkit_events-0.1.0/", "modkit_events-0.1.0/src/"):
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.DIRTYPE
                    writer.addfile(member)
                for name, content in fixture("sdist").items():
                    member = tarfile.TarInfo("modkit_events-0.1.0/" + name)
                    member.size = len(content)
                    writer.addfile(member, io.BytesIO(content))
            release.audit(target, "modkit-events", "0.1.0")

    def test_public_executable_sql_fixture_is_accepted(self):
        self.audit(
            "sdist",
            fixture("sdist")
            | {"tests/sql_specs/segment8_work_reader.sql": b"-- public SQL test\n"},
        )

    def test_existing_traversal_and_portable_alias_protections_remain(self):
        for kind in ("wheel", "sdist"):
            for path in (
                "../escape",
                "modkit_events/../escape",
                "modkit_events/CON.py",
                "modkit_events/PY.TYPED",
            ):
                with self.subTest(kind=kind, member=path):
                    with self.assertRaises(ValueError):
                        self.audit(kind, fixture(kind) | {path: b""})

    def test_archive_links_are_rejected_before_content_policy(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            directory = Path(temporary)
            wheel = archive(directory, "wheel", fixture("wheel"))
            with zipfile.ZipFile(wheel, "a") as writer:
                member = zipfile.ZipInfo("modkit_events/alias.py")
                member.create_system = 3
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                writer.writestr(member, "__init__.py")
            with self.assertRaisesRegex(ValueError, "symlink"):
                release.audit(wheel, "modkit-events", "0.1.0")
            target = directory / "linked.tar.gz"
            with clean_tar(target) as writer:
                member = tarfile.TarInfo("modkit_events-0.1.0/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "PKG-INFO"
                writer.addfile(member)
            with self.assertRaisesRegex(ValueError, "nonregular"):
                release.audit(target, "modkit-events", "0.1.0")

    def test_oversized_declared_tar_member_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "oversized.tar.gz"
            with clean_tar(target) as writer:
                member = tarfile.TarInfo("modkit_events-0.1.0/PKG-INFO")
                member.size = 3 * 1024 * 1024
                # Header only: there is intentionally no large file body.
                writer.fileobj.write(member.tobuf())
            with self.assertRaisesRegex(ValueError, "size limit"):
                release.audit(target, "modkit-events", "0.1.0")

    def test_oversized_metadata_is_rejected(self):
        for kind in ("wheel", "sdist"):
            with self.subTest(kind=kind):
                files = fixture(kind)
                key = next(name for name in files if name.endswith(("/METADATA", "PKG-INFO")))
                files[key] = METADATA + b"a" * (65 * 1024)
                with self.assertRaisesRegex(ValueError, "metadata size limit"):
                    self.audit(kind, files)

    def test_zip_directory_entry_count_is_bounded(self):
        files = fixture("wheel") | {f"unused/{i}": b"" for i in range(513)}
        with self.assertRaisesRegex(ValueError, "member count limit"):
            self.audit("wheel", files)

    def test_sparse_oversized_archive_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "oversized.whl"
            with target.open("wb") as writer:
                writer.truncate(16 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, "archive size limit"):
                release.audit(target, "modkit-events", "0.1.0")

    def test_tar_extended_header_request_is_bounded_before_allocation(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "pax.tar.gz"
            member = tarfile.TarInfo("extended")
            member.type = tarfile.XHDTYPE
            member.size = 3 * 1024 * 1024
            target.write_bytes(gzip.compress(member.tobuf()))
            with self.assertRaisesRegex(ValueError, "header read size limit"):
                release.audit(target, "modkit-events", "0.1.0")

    def test_tar_decompression_budget_stops_before_header_parsing(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "padding.tar.gz"
            target.write_bytes(gzip.compress(b"0" * 2048))
            # Scale only the resource budget; exercise the actual gzip reader.
            with patch.object(release, "MAX_TAR_BYTES", 1024):
                with self.assertRaisesRegex(ValueError, "decompressed size limit"):
                    release.audit(target, "modkit-events", "0.1.0")

    def test_aggregate_budget_applies_before_content_materialization(self):
        with patch.object(release, "MAX_TOTAL_BYTES", 32):
            for kind in ("wheel", "sdist"):
                with self.subTest(kind=kind):
                    with self.assertRaisesRegex(ValueError, "aggregate size limit"):
                        self.audit(kind, fixture(kind))

    def test_actual_member_read_must_match_declared_size(self):
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            release.bounded_read(io.BytesIO(b"abc"), 4)

    def test_installed_checker_rejects_policy_failure_before_venv_creation(self):
        checker_spec = importlib.util.spec_from_file_location(
            "wheel_policy_test", SCRIPTS / "check_wheel.py"
        )
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            files = fixture("wheel")
            files["modkit_events/__init__.py"] = b"/" + b"home/alice/private"
            target = archive(Path(temporary), "wheel", files)
            # A fail-fast boundary double prevents installation even if the policy regresses.
            with patch.object(sys, "argv", ["check_wheel.py", str(target)]):
                with patch.object(
                    checker.venv, "EnvBuilder", side_effect=AssertionError("must not install")
                ):
                    with self.assertRaisesRegex(ValueError, "private"):
                        checker.main()

    def test_noncanonical_metadata_root_is_rejected_before_metadata_content(self):
        files = fixture("wheel")
        del files["modkit_events-0.1.0.dist-info/METADATA"]
        files["other-0.1.0.dist-info/METADATA"] = b"invalid identity"
        with self.assertRaisesRegex(ValueError, "wheel metadata path"):
            self.audit("wheel", files)
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            target = Path(temporary) / "wrong-root.tar.gz"
            with clean_tar(target) as writer:
                member = tarfile.TarInfo("wrong-root/PKG-INFO")
                member.size = 3
                writer.addfile(member, io.BytesIO(b"bad"))
            with self.assertRaisesRegex(ValueError, "sdist root"):
                release.audit(target, "modkit-events", "0.1.0")

    def test_manifest_hash_tamper_remains_rejected(self):
        with tempfile.TemporaryDirectory(prefix="events-policy-fixture-") as temporary:
            directory = Path(temporary)
            for kind in ("wheel", "sdist"):
                archive(directory, kind, fixture(kind))
            sha = "a" * 40
            manifest_hash = release.create(directory, "modkit-events", "0.1.0", sha, "v0.1.0")
            release.verify(directory, manifest_hash, "modkit-events", sha, "v0.1.0")
            next(directory.glob("*.whl")).write_bytes(b"tamper")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                release.verify(directory, manifest_hash, "modkit-events", sha, "v0.1.0")


class PhysicalArchiveTests(unittest.TestCase):
    def check(self, data, wheel=True):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / ("fixture.whl" if wheel else "fixture.tar.gz")
            target.write_bytes(data)
            release.audit(target, "modkit-events", "0.1.0")

    def test_physical_zip_attacks(self):
        key = "modkit_events/__init__.py"
        private = b"/" + b"home/alice/private"
        plain = fixture("wheel")[key]
        compressed = zlib.compress(plain)[2:-4]
        cases = [
            {"name": key.encode() + b"\0" + private},
            {"payload": plain + private, "size": len(plain), "crc_plain": plain},
            {"extra": private},
            {"local_extra": private},
            {"comment": private},
            *(
                {"local": {index: value}}
                for index, value in ((0, 21), (1, 8), (2, 8), (3, 1), (5, 1), (6, 1), (7, 1))
            ),
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.check(raw_zip(fixture("wheel"), changed={key: options}))
        for options in (
            {"payload": plain + private, "size": len(plain), "crc_plain": plain},
            {"encoded": compressed[:-1]},
            {"encoded": compressed + private},
        ):
            with self.subTest(deflate=options), self.assertRaises(ValueError):
                self.check(raw_zip(fixture("wheel"), method=8, changed={key: options}))
        for data in (
            raw_zip(fixture("wheel"), comment=private),
            b"prefix" + raw_zip(fixture("wheel")),
            raw_zip(fixture("wheel")) + b"tail",
        ):
            with self.subTest(envelope=data[-30:]), self.assertRaises(ValueError):
                self.check(data)

    def test_actual_zip_count_precedes_standard_parser(self):
        data = raw_zip({f"item{i}": b"" for i in range(513)}, count=1)
        with patch.object(release.zipfile, "ZipFile", side_effect=AssertionError("parser entered")):
            with self.assertRaisesRegex(ValueError, "count limit"):
                self.check(data)

    def test_complete_inventory_required(self):
        for kind in ("wheel", "sdist"):
            names = list(EXPECTED_RUNTIME)
            names = [("src/" if kind == "sdist" else "") + name for name in names]
            if kind == "sdist":
                names += EXPECTED_SUPPORT
            for name in names:
                with self.subTest(kind=kind, missing=name):
                    files = fixture(kind)
                    del files[name]
                    with self.assertRaisesRegex(ValueError, "required"):
                        ArtifactPolicyTests().audit(kind, files)

    def test_backend_zip_profiles(self):
        for method in (0, 8):
            self.check(raw_zip(fixture("wheel"), method=method))

    def tar_bytes(self, *, fields=None, pax=None, global_pax=None):
        stream = io.BytesIO()
        with tarfile.open(
            fileobj=stream, mode="w", format=tarfile.PAX_FORMAT, pax_headers=global_pax
        ) as writer:
            for index, (name, content) in enumerate(fixture("sdist").items()):
                member = tarfile.TarInfo("modkit_events-0.1.0/" + name)
                member.size = len(content)
                if index == 0:
                    for key, value in (fields or {}).items():
                        setattr(member, key, value)
                    member.pax_headers = pax or {}
                writer.addfile(member, io.BytesIO(content))
        return stream.getvalue()

    def test_tar_metadata_channels(self):
        private = "/" + "home/alice/private"
        for field in ("uname", "gname", "linkname"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(gzip.compress(self.tar_bytes(fields={field: private})), False)
        for kwargs in (
            {"pax": {"comment": private}},
            {"global_pax": {"comment": private}},
            {"pax": {"mtime": private}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(gzip.compress(self.tar_bytes(**kwargs)), False)

    def test_gzip_metadata_and_framing(self):
        data = gzip.compress(self.tar_bytes())
        private = b"/" + b"home/alice/private"
        for flag, extra in (
            (8, private + b"\0"),
            (16, private + b"\0"),
            (4, struct.pack("<H", len(private)) + private),
        ):
            changed = data[:3] + bytes([flag]) + data[4:10] + extra + data[10:]
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.check(changed, False)
        for changed in (data + data, data + b"tail", data[:-1]):
            with self.subTest(tail=changed[-10:]), self.assertRaises(ValueError):
                self.check(changed, False)

    def test_pax_profile_positive(self):
        self.check(gzip.compress(self.tar_bytes(pax={"mtime": "1700000000.125"})), False)

    def test_extension_chain_rejected_before_recursive_parser(self):
        pax = tarfile.TarInfo("pax")
        pax.type = tarfile.XHDTYPE
        payload = b"11 mtime=0\n"
        pax.size = len(payload)
        block = pax.tobuf() + payload + bytes(512 - len(payload))
        data = gzip.compress(block * 513 + self.tar_bytes())
        with patch.object(
            release.tarfile, "open", side_effect=AssertionError("recursive parser entered")
        ):
            with self.assertRaises(ValueError):
                self.check(data, False)
        for kind in (tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            pax.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.check(
                    gzip.compress(
                        pax.tobuf() + payload + bytes(512 - len(payload)) + self.tar_bytes()
                    ),
                    False,
                )

    def test_physical_boundaries_without_standard_parser(self):
        with patch.object(release.zipfile, "ZipFile", side_effect=AssertionError("parser entered")):
            files, directories = release.physical_zip(
                raw_zip({f"item{i}": b"" for i in range(512)})
            )
            self.assertEqual(len(files), 512)
            self.assertEqual(directories, [])
        # 512 ordinary records are accepted at the physical layer; the 513th is rejected.
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as writer:
            for index in range(513):
                writer.addfile(tarfile.TarInfo(f"item{index}"))
        raw = stream.getvalue()
        with patch.object(release.tarfile, "open", side_effect=AssertionError("parser entered")):
            files, _ = release.physical_tar(gzip.compress(raw[: 512 * 512] + bytes(1024)))
            self.assertEqual(len(files), 512)
            with self.assertRaisesRegex(ValueError, "header count limit"):
                release.physical_tar(gzip.compress(raw))

    def test_pax_key_and_metadata_budgets(self):
        data = self.tar_bytes(pax={"mtime": "1700000000.125"})
        with patch.object(release, "MAX_METADATA_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "header read size limit"):
                self.check(gzip.compress(data), False)
        # Repeat valid one-key extensions separated by real members, avoiding chain rejection.
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as writer:
            for index in range(65):
                member = tarfile.TarInfo(f"item{index}")
                member.pax_headers = {"mtime": "1.25"}
                writer.addfile(member)
        with self.assertRaisesRegex(ValueError, "key count limit"):
            release.physical_tar(gzip.compress(stream.getvalue()))
        with patch.object(release, "MAX_METADATA_BYTES", 20):
            with self.assertRaisesRegex(ValueError, "cumulative metadata limit"):
                release.physical_tar(gzip.compress(stream.getvalue()))

    def test_tar_hidden_padding_and_header_tail(self):
        raw = self.tar_bytes()
        for changed in (raw + b"private", raw[:-1] + b"x"):
            with self.subTest(end=changed[-10:]), self.assertRaises(ValueError):
                self.check(gzip.compress(changed), False)
        header = bytearray(raw[:512])
        header[501] = 120
        header[148:156] = b"        "
        header[148:156] = f"{sum(header):06o}\0 ".encode()
        with self.assertRaisesRegex(ValueError, "unsupported tar header"):
            self.check(gzip.compress(bytes(header) + raw[512:]), False)

    def test_pax_canonical_path_and_fractional_mtime(self):
        first = next(iter(fixture("sdist")))
        self.check(
            gzip.compress(
                self.tar_bytes(
                    pax={"path": "modkit_events-0.1.0/" + first, "mtime": "1700000000.125"}
                )
            ),
            False,
        )


class InstalledWheelHarnessTests(unittest.TestCase):
    def test_staged_tests_keep_project_metadata_without_checkout_source(self):
        spec = importlib.util.spec_from_file_location(
            "check_wheel_staging_test", SCRIPTS / "check_wheel.py"
        )
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        with tempfile.TemporaryDirectory(prefix="modkit-staging-source-") as directory:
            root = Path(directory)
            for name in ("tests", "examples", "scripts", "src"):
                (root / name).mkdir()
            metadata = (SCRIPTS.parent / "pyproject.toml").read_bytes()
            (root / "pyproject.toml").write_bytes(metadata)
            (root / "tests/test_fixture.py").write_text("def test_fixture(): pass\n")
            (root / "examples/sample_app.py").write_text("pass\n")
            (root / "scripts/check_installation.py").write_text("pass\n")
            (root / "src/must_not_be_copied.py").write_text("raise AssertionError\n")
            wheel = root / "modkit_events-0.1.0-py3-none-any.whl"
            wheel.write_bytes(b"inert staging fixture")
            staged_runs = []

            def observe_command(command, *, cwd, env, check):
                if command[1:3] == ["-m", "pytest"]:
                    staged = Path(cwd)
                    self.assertTrue((staged / "pyproject.toml").is_file())
                    self.assertEqual((staged / "pyproject.toml").read_bytes(), metadata)
                    self.assertFalse((staged / "src").exists())
                    self.assertTrue((staged / "tests/test_fixture.py").is_file())
                    staged_runs.append(staged)

            with (
                patch.object(harness, "__file__", str(root / "scripts/check_wheel.py")),
                patch.object(sys, "argv", ["check_wheel.py", str(wheel)]),
                patch.object(harness, "audit"),
                patch.object(harness.venv.EnvBuilder, "create"),
                patch.object(harness.subprocess, "run", side_effect=observe_command),
            ):
                harness.main()
            self.assertEqual(len(staged_runs), 2)


if __name__ == "__main__":
    unittest.main()
