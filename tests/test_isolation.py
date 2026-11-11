import subprocess
import sys


def test_public_api_without_adapter_imports(tmp_path):
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
    # Select this actual product origin explicitly, with no environment/site startup.
    from pathlib import Path

    import modkit_events

    product = Path(modkit_events.__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "pycache_prefix=" + str(tmp_path / "unused-bytecode"),
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]);\n" + code,
            str(product),
        ],
        check=True,
    )
