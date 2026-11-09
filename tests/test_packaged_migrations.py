"""Actual candidate resource identity, NOT wheel/build qualification."""
import hashlib
import json
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


def test_import_origin_is_candidate_not_mirror_or_recovery():
    expected = Path(__file__).resolve().parents[1] / "src"
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name.startswith("modkit_events"):
            filename = getattr(module, "__file__", None)
            if filename:
                assert Path(filename).resolve().is_relative_to(expected)
                origins[name] = filename
    print("IMPORT_AUDIT", json.dumps(origins, sort_keys=True))
    assert not any(name.startswith(("psycopg", "sqlalchemy", "modkit_workers")) for name in sys.modules)
