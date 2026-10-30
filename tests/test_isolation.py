import subprocess
import sys


def test_public_api_without_adapter_imports():
    code = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'redis', 'sqlalchemy', 'operations_erp', 'modkit_diagnostics'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import modkit_events as m
for name in m.__all__:
    assert getattr(m, name) is not None
assert m.JsonCodec().decode(m.JsonCodec().encode(m.Event('1', 'a', {}))).event_id == '1'
"""
    # Parent pytest's pythonpath setting is not inherited by subprocesses.
    import os
    from pathlib import Path

    import modkit_events

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(modkit_events.__file__).parents[1])
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
