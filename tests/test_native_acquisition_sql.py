"""Bounded E04 source contracts only; no SQL/runtime qualification."""

import hashlib
import re
from importlib.resources import files

from modkit_events.persistence.catalog import get_statement

PREFIX_BYTES = 400012
PREFIX_SHA = "0410fdff4d6e4d02b2d25bdc1135623d817bda1f65b6f1d6d7c1fce16b4cddf0"


def source():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_bytes()


def bounded():
    appended = source()[PREFIX_BYTES:].decode()
    assert "CREATE FUNCTION modkit_events.e04(" in appended, "bounded E04 overload missing"
    return appended[: appended.index("$body$;") + len("$body$;")]


def test_bounded_acquire_preserves_complete_e13_prefix_and_exact_abi():
    assert hashlib.sha256(source()[:PREFIX_BYTES]).hexdigest() == PREFIX_SHA
    body = bounded()
    inputs, outputs = body.split("RETURNS TABLE(", 1)
    assert "p_max_page_payload_bytes pg_catalog.int8" in inputs
    assert inputs.count("p_namespace pg_catalog.bytea") == 1
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", outputs.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in get_statement("E04").result.columns
    ]
    assert "VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in body
    assert "SET search_path = pg_catalog, pg_temp" in body


def test_bounded_acquire_guards_precede_semantics_mutation_and_array_growth():
    body = bounded()
    assert body.index("p_max_page_payload_bytes NOT BETWEEN 1 AND 4294967296") < body.index(
        "WHILE visited_count"
    )
    assert body.index("invalid candidate field width") < body.index(
        "CROSS JOIN LATERAL modkit_events.e15"
    )
    assert body.index("expected acquisition payload exceeds budget") < body.index(
        "UPDATE modkit_events.work"
    )
    assert body.index("returned acquisition payload exceeds budget") < body.index(
        "pg_catalog.array_append"
    )
    assert "retained_payload_bytes := 6" in body
    assert "row_payload_bytes := 4::pg_catalog.int8" in body
    assert "retained_payload_bytes := retained_payload_bytes+row_payload_bytes" in body
    assert body.index("header exceeds acquisition budget") < body.index("WHILE visited_count")
    assert "EXCEPTION WHEN" not in body
    assert "COMMIT" not in body and "ROLLBACK" not in body


def test_bounded_acquire_every_variable_work_occurrence_is_charged_as_int8():
    body = bounded()
    columns = get_statement("E15").result.columns[:39]
    for col in columns:
        if col.wire_type.value not in ("bytea", "text"):
            continue
        for alias in ("expected_work", "updated_work"):
            value = alias + "." + col.name
            arg = (
                "pg_catalog.convert_to(" + value + ",'UTF8')"
                if col.wire_type.value == "text"
                else value
            )
            assert "COALESCE(pg_catalog.octet_length(" + arg + ")::pg_catalog.int8,0)" in body
    assert body.count("pg_catalog.array_append(emitted_rows,updated_work)") == 1
    assert body.count("CROSS JOIN LATERAL modkit_events.e15") == 1
    assert "RETURN QUERY SELECT 'header'" in body and "RETURN QUERY SELECT 'item'" in body


def test_bounded_acquire_keeps_exact_float_and_private_new_signature():
    body = bounded()
    assert "lease_wire := pg_catalog.float8send(p_lease_seconds)" in body
    assert "pg_catalog.div(numerator+denominator-1,denominator)" in body
    assert "RETURNING stored.* INTO updated_work" in body
    appended = source()[PREFIX_BYTES:].decode()
    signature = "modkit_events.e04(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea[],pg_catalog.int4[],pg_catalog.int4,pg_catalog.float8,pg_catalog.uuid,pg_catalog.int4,pg_catalog.int8)"
    assert "REVOKE ALL ON FUNCTION " + signature + " FROM PUBLIC;" in appended
    assert "acl.grantee<>p.proowner" in appended
    assert "unsafe private bounded Events acquisition boundary" in appended
