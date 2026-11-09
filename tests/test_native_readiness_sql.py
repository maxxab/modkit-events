"""Static source boundary tests. No SQL execution or migration readiness claim."""

from _installation_artifact_helpers import historical_prefix_view

from hashlib import sha256
from pathlib import Path

from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.native_codec import _selected_sql_descriptor


def test_e33_append_only_read_only_sql():
    raw = (
        Path(__file__).parents[1] / "src/modkit_events/persistence/sql/0001_initial.sql"
    ).read_bytes()
    assert sha256(historical_prefix_view(raw)[:471491]).hexdigest() == (
        "34ee692ce56bf4268239991e7366aeada393547c4fda7b7263b02c4fa3dae83e"
    )
    addition = historical_prefix_view(raw)[471491:].decode()
    assert "CREATE FUNCTION modkit_events.e33(" in addition
    assert "STABLE SECURITY DEFINER" in addition
    assert "REVOKE ALL ON FUNCTION modkit_events.e33(pg_catalog.text) FROM PUBLIC;" in addition
    body = addition.split("AS $body$")[1].split("$body$")[0]
    for token in (
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "COMMIT",
        "ROLLBACK",
        "GRANT ",
        "CREATE ",
        "FOR UPDATE",
        "EXECUTE ",
    ):
        assert token not in body.upper()
    sql = _selected_sql_descriptor(get_statement("E33")).sql
    assert b"modkit_events.e33($1::pg_catalog.text)" in sql
    assert sql.rfind(b"ORDER BY") > sql.rfind(b"FROM checked")
    assert sql.rstrip().endswith(b"LIMIT 3")


def test_e33_driver_sql_uses_catalog_operators_independent_of_search_path():
    # The raw issuer query runs on a caller-owned connection, unlike the
    # function body with its pinned search_path. Do not resolve operators there
    # through a caller's earlier schema.
    sql = _selected_sql_descriptor(get_statement("E33")).sql
    assert sql.count(b"OPERATOR(pg_catalog.<=)") == 5
    assert sql.count(b"OPERATOR(pg_catalog.=)") == 1
