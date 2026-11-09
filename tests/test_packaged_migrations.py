"""Actual candidate resource identity, NOT wheel/build qualification."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from modkit_events.persistence import migrations as m


def test_actual_manifest_independent_mkmf_oracle():
    sql = Path(m.__file__).parent / "sql"
    document = json.loads((sql / "manifest.json").read_bytes())
    assert set(document) == {"format_version", "package", "migrations"}
    assert document["package"] == "modkit-events"
    entry, = document["migrations"]
    expected_paths = ["events/0001_initial.sql", "events/grants_runtime.sql"]
    assert [r["path"] for r in entry["resources"]] == expected_paths
    frame = b"MKMF\x01" + (2).to_bytes(4, "big")
    for item in sorted(entry["resources"], key=lambda x: x["path"].encode()):
        path = item["path"].encode()
        actual = hashlib.sha256((sql / item["path"].split("/")[1]).read_bytes()).digest()
        assert actual.hex() == item["sha256"]
        frame += len(path).to_bytes(4, "big") + path + actual
    assert hashlib.sha256(frame).hexdigest() == entry["migration_digest"]
    assert entry["depends_on"] == []
    migration, = m.manifest()
    assert migration.migration_digest == entry["migration_digest"]
    for resource in migration.resources:
        assert m.read_sql(migration, resource).encode() == (sql / resource.path.split("/")[1]).read_bytes()


def test_import_origin_is_candidate_not_mirror_or_recovery(tmp_path):
    # Other source tests may intentionally import optional drivers. Verify the
    # inert resource boundary in a fresh interpreter instead of shared state.
    expected = Path(__file__).resolve().parents[1] / "src"
    script = r"""
import importlib.abc
import json
import sys
from pathlib import Path

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert sys.pycache_prefix and not Path(sys.pycache_prefix).exists()
expected = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(expected))
class NoDriversOrWorkers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'psycopg', 'sqlalchemy', 'modkit_workers'}:
            raise AssertionError('Resource import attempted optional dependency')
sys.meta_path.insert(0, NoDriversOrWorkers())
from modkit_events.persistence import migrations
migration, = migrations.manifest()
for resource in migration.resources:
    assert migrations.read_sql(migration, resource)
origins = {}
for name, module in tuple(sys.modules.items()):
    if name.startswith('modkit_events') and getattr(module, '__file__', None):
        assert Path(module.__file__).resolve().is_relative_to(expected)
        origins[name] = module.__file__
assert origins
assert not any(name.startswith(('psycopg', 'sqlalchemy', 'modkit_workers')) for name in sys.modules)
print('IMPORT_AUDIT', json.dumps(origins, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-X",
         "pycache_prefix=" + str(tmp_path / "unused-bytecode"), "-c", script, str(expected)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT_AUDIT" in result.stdout
