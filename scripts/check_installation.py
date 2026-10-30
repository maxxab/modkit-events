"""Verify the imported distribution really belongs to the clean environment."""

from pathlib import Path


def assert_installation(
    module_path: Path, prefix: Path, actual_version: str, expected_version: str
):
    assert module_path.resolve().is_relative_to(prefix.resolve()), (
        "module is outside installed venv"
    )
    assert actual_version == expected_version, "installed metadata version mismatch"


def main():
    import importlib.metadata as metadata
    import sys

    import modkit_events

    assert_installation(
        Path(modkit_events.__file__),
        Path(sys.prefix),
        metadata.version("modkit-events"),
        sys.argv[1],
    )
    siblings = {"modkit-api-responses", "modkit-api-versioning", "modkit-diagnostics"}
    assert not any(
        dist.metadata["Name"].lower().replace("_", "-") in siblings
        for dist in metadata.distributions()
    ), "unexpected sibling distribution"


if __name__ == "__main__":
    main()
