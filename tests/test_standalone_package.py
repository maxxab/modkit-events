"""Events has no reverse dependency on the separately distributed Workers package."""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_events_source_and_default_tests_do_not_import_workers():
    # Catches moving a Workers integration back into Events' default test lane.
    violations = []
    for directory in ("src", "tests"):
        for path in (_ROOT / directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name.split(".")[0] == "modkit_workers" for name in names):
                    violations.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not violations, "Events must not import Workers: " + ", ".join(violations)


def test_events_metadata_never_requires_workers():
    # Both ordinary dependencies and all optional extras must remain one-way.
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    assert not any("modkit-workers" in item.lower().replace("_", "-") for item in requirements)


def test_events_core_and_migration_contract_work_with_workers_blocked(tmp_path):
    # A reverse runtime import fails even when a developer has Workers installed.
    script = r"""
import asyncio
import hashlib
import importlib.abc
import sys

sys.path.insert(0, sys.argv[1])
class NoWorkers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'modkit_workers':
            raise AssertionError('Events attempted to import Workers: ' + fullname)
sys.meta_path.insert(0, NoWorkers())

from modkit_events import Consumer, Dispatcher, Event, JsonCodec, MemoryClaimStore
from modkit_events.persistence import bindings, catalog, migrations, observations, rows

async def main():
    seen = []
    async def handler(event):
        seen.append(event.event_id)
    dispatcher = Dispatcher()
    dispatcher.subscribe('standalone', handler)
    consumer = Consumer(MemoryClaimStore(), dispatcher, scope='standalone')
    event = Event('one', 'standalone', {'nested': [1, True, None]})
    codec = JsonCodec()
    assert codec.decode(codec.encode(event)) == event
    assert await consumer.consume(event) == 'processed'
    assert await consumer.consume(event) == 'completed'
    assert seen == ['one']
asyncio.run(main())

resources = tuple(migrations.SQLResource(path='events/' + name, sha256='0' * 64)
                  for name in ('0001_initial.sql', 'grants_runtime.sql'))
digest = hashlib.sha256(b'MKMF\x01' + len(resources).to_bytes(4, 'big'))
for resource in sorted(resources, key=lambda item: item.path):
    path = resource.path.encode()
    digest.update(len(path).to_bytes(4, 'big') + path + bytes.fromhex(resource.sha256))
fields = dict(component='events', version=1, resources=resources,
              migration_digest=digest.hexdigest(), depends_on=(),
              catalog_contract_id='modkit-pg-ab-2', scope_format_id='MKSC-1',
              intent_format_id='MKPF-1')
assert migrations.Migration(**fields).depends_on == ()
try:
    migrations.Migration(**{**fields, 'depends_on': (
        migrations.MigrationDependency(component='workers', version=1, migration_digest='0'*64),)})
except ValueError:
    pass
else:
    raise AssertionError('Events migration accepted a Workers dependency')
status = observations.SchemaStatus(**{key: value for key, value in fields.items()
                                     if key not in ('resources', 'depends_on', 'migration_digest')},
                                   migration_digest=bytes.fromhex(digest.hexdigest()))
request = bindings.freeze_request(catalog.get_statement('E33'), ['events'],
    context=bindings.ReturnContext(expected=(), readiness=bindings.ReadinessExpectation(
        components=(status,))))
wire = tuple(getattr(status, column.name) for column in request.statement.result.columns)
assert rows.decode_event_rows(request, [wire]) == (status,)
# This is contract validation, not a live PostgreSQL migration or readiness claim.
assert not any(name.split('.')[0] == 'modkit_workers' for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(_ROOT / "src")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
