"""Offline controls for the fresh synthetic PostgreSQL CI lane."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_postgres.py"


def load_script():
    assert SCRIPT.is_file(), "PostgreSQL CI checker has not been implemented"
    spec = importlib.util.spec_from_file_location("events_postgres_ci_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ci_env():
    return {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "maxxab/modkit-events",
        "MODKIT_POSTGRES_TEST": "events-installation-v1",
    }


def test_exact_synthetic_ci_context_is_required():
    module = load_script()
    module.require_ci_environment(ci_env())
    for key in ci_env():
        env = ci_env()
        del env[key]
        with pytest.raises(ValueError, match="synthetic GitHub CI"):
            module.require_ci_environment(env)
        env[key] = "different"
        with pytest.raises(ValueError, match="synthetic GitHub CI"):
            module.require_ci_environment(env)


@pytest.mark.parametrize("key", ["PGHOST", "PGSERVICE", "PGPASSFILE", "PGOPTIONS", "PGPASSWORD"])
def test_existing_postgres_environment_is_rejected(key):
    module = load_script()
    with pytest.raises(ValueError, match="PostgreSQL environment"):
        module.require_ci_environment({**ci_env(), key: "must-not-be-used"})


def test_connection_target_cannot_be_selected_by_caller():
    module = load_script()
    for name in module.LOGIN_ROLES:
        settings = module.connection_options(name)
        assert settings["host"] == settings["hostaddr"] == "127.0.0.1"
        assert settings["port"] == 5432
        assert settings["dbname"] == "modkit_events_ci"
        assert settings["connect_timeout"] == 5
        assert settings["user"] == name
        assert settings["passfile"] == "/dev/null"
        assert settings["service"] == ""
    with pytest.raises(ValueError, match="unknown fixture login"):
        module.connection_options("postgres")


def test_server_preflight_rejects_wrong_or_used_targets():
    module = load_script()
    row = (171100, "modkit_events_ci", "modkit_ci_bootstrap", "modkit_ci_bootstrap")
    module.validate_target(row, ["modkit_ci_bootstrap"], [], [])
    for index, changed in enumerate((160000, "existing_app", "owner", "owner")):
        bad = list(row)
        bad[index] = changed
        with pytest.raises(ValueError, match="fresh synthetic PostgreSQL 17"):
            module.validate_target(tuple(bad), ["modkit_ci_bootstrap"], [], [])
    for roles, schemas in (
        (["modkit_ci_bootstrap", "existing_user"], []),
        (["modkit_ci_bootstrap"], ["existing_app"]),
    ):
        with pytest.raises(ValueError, match="fresh synthetic PostgreSQL 17"):
            module.validate_target(row, roles, schemas, [])


def test_execute_matrix_keeps_private_and_worker_only_overload_closed():
    module = load_script()
    all_roles = {"modkit_runtime", "modkit_reconciler", "modkit_operator"}
    assert module.expected_function_roles("e33", 1) == all_roles
    assert module.expected_function_roles("e14", 0) == all_roles - {"modkit_operator"}
    assert module.expected_function_roles("e04", 8) == {"modkit_runtime"}
    assert module.expected_function_roles("e04", 9) == set()
    assert module.expected_function_roles("_utf8_valid", 3) == set()
    assert module.expected_function_roles("e12", 4) == {"modkit_reconciler"}
    assert module.expected_function_roles("e32", 10) == {"modkit_runtime"}
    with pytest.raises(ValueError, match="unexpected public function"):
        module.expected_function_roles("e35", 0)


def test_all_public_function_names_have_one_explicit_permission_class():
    module = load_script()
    groups = [module.READ_FUNCTIONS, module.RUNTIME_FUNCTIONS, module.RECONCILER_FUNCTIONS, {"e14"}]
    assert set.union(*groups) == {f"e{number:02}" for number in range(1, 35)}
    assert sum(map(len, groups)) == 34


def test_main_refuses_before_package_or_driver_import(monkeypatch):
    import builtins

    module = load_script()
    monkeypatch.setattr(module.os, "environ", {})
    original = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.startswith(("psycopg", "modkit_events")), "guard ran too late"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(ValueError, match="synthetic GitHub CI"):
        module.main()


def test_existing_public_objects_are_rejected_before_bootstrap():
    import inspect

    module = load_script()
    assert "objects" in inspect.signature(module.validate_target).parameters, (
        "target guard must inspect objects even in the default public schema"
    )
    row = (171100, "modkit_events_ci", "modkit_ci_bootstrap", "modkit_ci_bootstrap")
    module.validate_target(row, ["modkit_ci_bootstrap"], [], [])
    for objects in (
        [("relation", "public.existing_table")],
        [("function", "public.existing_function")],
        [("type", "public.existing_enum")],
    ):
        with pytest.raises(ValueError, match="fresh synthetic PostgreSQL 17"):
            module.validate_target(row, ["modkit_ci_bootstrap"], [], objects)
