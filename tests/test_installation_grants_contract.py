"""Connection-free contract checks, not SQL execution or ACL qualification."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "src/modkit_events/persistence/sql"
EXPECTED = {
    "modkit_events._utf8_valid(pg_catalog.bytea,pg_catalog.int4,pg_catalog.bool)": [],
    "modkit_events._bounded_uint(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4)": [],
    "modkit_events._scope_valid(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [],
    "modkit_events._record_fields(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._decimal_valid(pg_catalog.bytea,pg_catalog.bool)": [],
    "modkit_events._float_hex_valid(pg_catalog.bytea)": [],
    "modkit_events._j_nodes(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4)": [],
    "modkit_events._integer_power(pg_catalog.int4,pg_catalog.int4)": [],
    "modkit_events._hex_fraction(pg_catalog.numeric)": [],
    "modkit_events._decimal_float_hex(pg_catalog.bytea)": [],
    "modkit_events._hex4(pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._utf8_scalar(pg_catalog.int4)": [],
    "modkit_events._json_string_chunks(pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._json_string(pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._skip_json_ws(pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._json_children(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4)": [],
    "modkit_events._json_value(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4)": [],
    "modkit_events._json_to_j(pg_catalog.bytea)": [],
    "modkit_events._make_record(pg_catalog.bytea,pg_catalog.bytea[])": [],
    "modkit_events._j_scalar_bytes(pg_catalog.bytea,pg_catalog.int4)": [],
    "modkit_events._event_replay_frame(pg_catalog.bytea)": [],
    "modkit_events._optional_bytes(pg_catalog.bytea)": [],
    "modkit_events._instant_bytes(pg_catalog.timestamptz)": [],
    "modkit_events._protected_valid(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea)": [],
    "modkit_events._intent_valid(pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.timestamptz,pg_catalog.timestamptz)": [],
    "modkit_events._guard_immutable()": [],
    "modkit_events._guard_deferred_check()": [],
    "modkit_events._reject_record_mutation()": [],
    "modkit_events._attempt_record_check()": [],
    "modkit_events.e14()": ["modkit_runtime", "modkit_reconciler"],
    "modkit_events.e09(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e08(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4)": [
        "modkit_runtime"
    ],
    "modkit_events._protected_frame_valid(pg_catalog.bytea)": [],
    "modkit_events._job_payload_record_check()": [],
    "modkit_events._inbox_record_check()": [],
    "modkit_events._work_admission_immutable()": [],
    "modkit_events.e10(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.xid8,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e15(pg_catalog.uuid)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e18(pg_catalog.bytea)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e17(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e16(pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e34(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e01(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4)": [
        "modkit_runtime"
    ],
    "modkit_events.e03(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.timestamptz,pg_catalog.timestamptz,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bool,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e28(pg_catalog.bytea)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e02(pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e04(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea[],pg_catalog.int4[],pg_catalog.int4,pg_catalog.float8,pg_catalog.uuid,pg_catalog.int4)": [
        "modkit_runtime"
    ],
    "modkit_events.e05(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.float8)": [
        "modkit_runtime"
    ],
    "modkit_events.e06(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.uuid,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e07(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.timestamptz)": [
        "modkit_runtime"
    ],
    "modkit_events.e30(pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.uuid,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e19(pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e20(pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e21(pg_catalog.uuid,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e29(pg_catalog.bytea,pg_catalog.int8,pg_catalog.int4)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e22(pg_catalog.int4,pg_catalog.float8,pg_catalog.bytea,pg_catalog.int4)": [
        "modkit_runtime"
    ],
    "modkit_events.e23(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.float8)": [
        "modkit_runtime"
    ],
    "modkit_events.e24(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.uuid)": [
        "modkit_runtime"
    ],
    "modkit_events.e25(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e26(pg_catalog.int4,pg_catalog.bytea,pg_catalog.int4)": ["modkit_reconciler"],
    "modkit_events.e27(pg_catalog.bytea,pg_catalog.int8,pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_reconciler"
    ],
    "modkit_events.e12(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.text)": [
        "modkit_reconciler"
    ],
    "modkit_events.e13(pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.uuid,pg_catalog.int4)": [
        "modkit_reconciler"
    ],
    "modkit_events.e04(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea[],pg_catalog.int4[],pg_catalog.int4,pg_catalog.float8,pg_catalog.uuid,pg_catalog.int4,pg_catalog.int8)": [],
    "modkit_events.e11(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.xid8,pg_catalog.text,pg_catalog.timestamptz,pg_catalog.text,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e32(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.xid8,pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_runtime"
    ],
    "modkit_events.e33(pg_catalog.text)": [
        "modkit_runtime",
        "modkit_reconciler",
        "modkit_operator",
    ],
    "modkit_events.e31(pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.uuid,pg_catalog.uuid,pg_catalog.text,pg_catalog.timestamptz,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea)": [
        "modkit_reconciler"
    ],
}
BASE_SUFFIX_SHA = "8b5dd65194ecce01af5379b0acfbdc8934f1ff558b8e1af0a15e313a7f4f639c"


def test_initial_preserves_exact_functional_suffix():
    raw = (SQL / "0001_initial.sql").read_bytes()
    assert raw.splitlines()[0] == b"-- Events initial schema for explicit owner installation."
    assert (
        hashlib.sha256(b"".join(raw.splitlines(keepends=True)[3:])).hexdigest() == BASE_SUFFIX_SHA
    )


def test_grants_are_exact_selected_signature_role_pairs():
    text = (SQL / "grants_runtime.sql").read_text()
    actual = {}
    for signature, roles in re.findall(r"GRANT EXECUTE ON FUNCTION ([^;]+) TO ([^;]+);", text):
        assert signature not in actual
        actual[signature] = roles.split(",")
    assert actual == {sig: roles for sig, roles in EXPECTED.items() if roles}
    schemas = re.findall(r"GRANT USAGE ON SCHEMA modkit_events TO ([^;]+);", text)
    assert schemas == ["modkit_runtime,modkit_reconciler,modkit_operator"]


def test_grants_no_unbounded_or_mutating_control_surface():
    text = (SQL / "grants_runtime.sql").read_text()
    executable = re.sub(r"--[^\n]*", "", text)
    for forbidden in (
        r"GRANT\s+ALL",
        r"ALL FUNCTIONS",
        r"ALTER DEFAULT",
        r"CREATE ROLE",
        r"ALTER ROLE",
        r"SET ROLE",
        r"COMMIT\s*;",
        r"ROLLBACK\s*;",
        r"GRANT .* ON (?:TABLE|SEQUENCE|TYPE)",
        r"REVOKE ",
    ):
        assert not re.search(forbidden, executable, re.I), forbidden


def test_grants_have_closed_catalog_and_effective_privilege_oracles():
    text = (SQL / "grants_runtime.sql").read_text()
    for token in (
        "pg_default_acl",
        "defaclnamespace",
        "pg_auth_members",
        "rolinherit",
        "set_option",
        "attacl",
        "has_column_privilege",
        "has_table_privilege",
        "has_sequence_privilege",
        "has_function_privilege",
        "has_schema_privilege",
        "has_type_privilege",
        "typacl",
        "typelem",
        "typarray",
        "prosrc",
        "proallargtypes",
        "proargnames",
        "proargmodes",
        "proconfig",
        "prosecdef",
        "is_grantable",
        "EXCEPT",
        "PZ011",
        "preflight",
        "postflight",
    ):
        assert token in text, token
    # Literal inventory includes every private function, rather than just public grants.
    for signature in EXPECTED:
        assert "'" + signature + "'" in text


def test_json_inventory_matches_all_frozen_initial_bodies_and_abis():
    import json

    grants = (SQL / "grants_runtime.sql").read_text()
    inventories = re.findall(r"\$functions\$(.*?)\$functions\$", grants, re.S)
    assert len(inventories) == 2 and inventories[0] == inventories[1]
    items = json.loads(inventories[0])
    assert len(items) == len(EXPECTED)
    initial = (SQL / "0001_initial.sql").read_text()
    for item in items:
        signature = item["signature"]
        assert item["roles"] == EXPECTED[signature]
        name = signature.split("(")[0]
        candidates = re.findall(
            r"CREATE FUNCTION "
            + re.escape(name)
            + r"\((.*?)\)\s*RETURNS (.*?)\s+LANGUAGE plpgsql(.*?)AS \$body\$(.*?)\$body\$;",
            initial,
            re.S,
        )
        selected = []
        for parameters, returns, options, body in candidates:
            params = re.findall(r"(\w+)\s+((?:pg_catalog|modkit_events)\.\w+(?:\[\])?)", parameters)
            if name + "(" + ",".join(t for _, t in params) + ")" == signature:
                selected.append((params, returns, options, body))
        assert len(selected) == 1
        params, returns, options, body = selected[0]
        assert item["body_sha256"] == hashlib.sha256(body.encode()).hexdigest()
        assert item["input_types"] == [t for _, t in params]
        assert item["definer"] == ("SECURITY DEFINER" in options)
        assert item["setof"] == returns.startswith("TABLE")
    assert "SELECT x.*,n FROM" not in grants, "duplicate ordinality field in column loop"


def test_function_and_schema_acl_checks_are_bidirectional_and_typed():
    text = (SQL / "grants_runtime.sql").read_text()
    assert text.count("SELECT * FROM actual_acl EXCEPT SELECT * FROM wanted") == 4
    assert text.count("SELECT * FROM wanted EXCEPT SELECT * FROM actual_acl") == 4
    assert "postflight AND rolname=ANY(allowed_roles)" in text
    assert "d.defaclrole=owner_oid AND d.defaclnamespace IN (0,schema_oid)" in text
    assert "a.typacl IS NULL" in text and "ELSIF typ.typacl IS NOT NULL" in text
    assert "has_type_privilege(role_oid,typ.typarray,'USAGE')" in text
    assert "has_column_privilege(role_oid,object_oid,a.attnum" in text


def test_closed_indexes_and_trigger_call_targets():
    text = (SQL / "grants_runtime.sql").read_text()
    assert "index_names CONSTANT" in text
    assert "c.relname=ANY(index_names)" in text
    assert "tgisinternal" in text and "tgfoid" in text and "tgenabled" in text
    assert "unexpected Events trigger" in text


def _function_acl_plan_baselines():
    """Interpret only the fixed SELECT/filter subset used by the two ACL CTEs.

    PostgreSQL function defaults have owner EXECUTE plus PUBLIC EXECUTE.
    This finite set oracle is not PostgreSQL execution or native qualification.
    Unknown SQL shapes fail rather than being guessed.
    """
    source = (SQL / "grants_runtime.sql").read_text()
    pattern = (
        r"WITH actual_acl AS \(\s*"
        r"SELECT grantor,grantee,privilege_type,is_grantable\s*"
        r"FROM pg_catalog\.aclexplode\(COALESCE\(actual\.proacl,"
        r"pg_catalog\.acldefault\('f',owner_oid\)\)\)\s*"
        r"\), wanted AS \(\s*"
        r"SELECT grantor,grantee,privilege_type,is_grantable\s*"
        r"FROM pg_catalog\.aclexplode\(pg_catalog\.acldefault\('f',owner_oid\)\)"
        r"(?P<filter>.*?)UNION ALL\s*"
        r"SELECT owner_oid,oid,'EXECUTE'::pg_catalog\.text,FALSE "
        r"FROM pg_catalog\.pg_roles\s*"
        r"WHERE postflight AND rolname=ANY\(allowed_roles\)\s*\)"
    )
    plans = list(re.finditer(pattern, source, re.S))
    assert len(plans) == 2, "actual/default expansion or fixed wanted SQL changed"
    default_acl = {(10, 10, "EXECUTE", False), (10, 0, "EXECUTE", False)}
    for match in plans:
        predicate = " ".join(match["filter"].split())
        assert predicate in ("", "WHERE grantee=owner_oid"), predicate
        yield {row for row in default_acl if not predicate or row[1] == 10}, default_acl


def test_sr1_revoked_initial_and_exact_postgrant_acl_sets():
    owner_only = {(10, 10, "EXECUTE", False)}
    for baseline, default_acl in _function_acl_plan_baselines():
        assert default_acl != owner_only, "PUBLIC default must not be erased from actual"
        for permitted in ((), (11,), (12,), (11, 12), (11, 12, 13)):
            for postflight in (False, True):
                grants = (
                    {(10, role, "EXECUTE", False) for role in permitted} if postflight else set()
                )
                expected = baseline | grants
                legitimate_actual = owner_only | grants
                # Both EXCEPT directions must be empty for legitimate exact state.
                assert not (expected - legitimate_actual), "wanted requires spurious PUBLIC"
                assert not (legitimate_actual - expected), "wanted misses intended exact grant"


def test_sr1_public_default_and_mutated_acl_sets_rejected():
    owner_only = {(10, 10, "EXECUTE", False)}
    for baseline, default_acl in _function_acl_plan_baselines():
        for postflight in (False, True):
            grants = {(10, 11, "EXECUTE", False)} if postflight else set()
            expected = baseline | grants
            legitimate = owner_only | grants
            invalid_states = [
                default_acl | grants,  # NULL actual ACL expands to PUBLIC, never filtered.
                legitimate | {(10, 0, "EXECUTE", False)},
                legitimate | {(10, 99, "EXECUTE", False)},  # unexpected grantee
                legitimate | {(99, 11, "EXECUTE", False)},  # unexpected grantor
                legitimate | {(10, 11, "EXECUTE", True)},  # grant option
                legitimate | {(10, 11, "USAGE", False)},  # wrong privilege
                grants,  # missing owner entry
            ]
            if postflight:
                invalid_states.append(owner_only)  # missing required direct grant
            for actual in invalid_states:
                assert (actual - expected) or (expected - actual), (
                    "contaminated ACL unexpectedly equals wanted",
                    actual,
                    postflight,
                )


def test_job_payload_inventory_has_only_actual_declared_columns():
    """CHECK-expression continuation tokens must never become catalog columns."""
    import json

    # Independent reviewed table ABI, including nullability and physical order.
    expected = [
        ("job_work_id", "pg_catalog.uuid", True),
        ("job_application", "pg_catalog.bytea", True),
        ("job_tenant", "pg_catalog.bytea", False),
        ("job_owner", "pg_catalog.bytea", False),
        ("job_protected_binding", "pg_catalog.bytea", True),
        ("job_semantic_input", "pg_catalog.bytea", True),
        ("material_state", "pg_catalog.text", True),
        ("protected_sidecar", "pg_catalog.bytea", False),
        ("protected_reference", "pg_catalog.bytea", False),
        ("protected_codec", "pg_catalog.bytea", False),
        ("protected_key_version", "pg_catalog.bytea", False),
        ("protected_expires_at", "pg_catalog.timestamptz", False),
        ("protected_recovery_metadata", "pg_catalog.bytea", True),
        ("protected_cleanup_policy", "pg_catalog.text", True),
        ("projection_metadata", "pg_catalog.bytea", True),
    ]
    initial = (SQL / "0001_initial.sql").read_text()
    declaration = initial.split("CREATE TABLE modkit_events.job_payloads (", 1)[1]
    declaration = declaration.split("    CONSTRAINT job_payloads_pkey", 1)[0]
    actual = []
    for line in declaration.splitlines():
        if not line.strip():
            continue
        name, wire, *constraints = line.strip().rstrip(",").split()
        assert constraints in ([], ["NOT", "NULL"])
        actual.append((name, wire, constraints == ["NOT", "NULL"]))
    assert actual == expected
    inventories = re.findall(
        r"\$relations\$(.*?)\$relations\$", (SQL / "grants_runtime.sql").read_text(), re.S
    )
    assert len(inventories) == 2 and inventories[0] == inventories[1]
    for raw in inventories:
        relations = json.loads(raw)
        for relation in relations:
            names = [column["name"] for column in relation["columns"]]
            assert len(names) == len(set(names)), relation["name"]
        payload = next(row for row in relations if row["name"] == "job_payloads")
        assert [
            (col["name"], col["type"], col["notnull"]) for col in payload["columns"]
        ] == expected


def test_mutation_retry_at_check_does_not_imply_not_null_column():
    import json

    initial = (SQL / "0001_initial.sql").read_text()
    table = initial.split("CREATE TABLE modkit_events.mutation_operations (", 1)[1]
    declaration = table.split("\n", 1)[1]
    retry = next(
        line.strip()
        for line in declaration.splitlines()
        if line.strip().startswith("retry_at pg_catalog.timestamptz")
    )
    assert retry.startswith("retry_at pg_catalog.timestamptz CHECK (")
    assert "retry_at IS NULL OR" in retry and "IS NOT NULL" in retry
    for raw in re.findall(
        r"\$relations\$(.*?)\$relations\$", (SQL / "grants_runtime.sql").read_text(), re.S
    ):
        relation = next(row for row in json.loads(raw) if row["name"] == "mutation_operations")
        column = next(row for row in relation["columns"] if row["name"] == "retry_at")
        assert column == {"name": "retry_at", "type": "pg_catalog.timestamptz", "notnull": False}


def test_type_topology_if_keeps_case_then_inside_sql_parentheses():
    """Static regression for the actual PG18.1 PL/pgSQL compile failure.

    PL/pgSQL reads an IF expression through its first top-level THEN. The
    SQL CASE's THEN must stay within parentheses. Native compilation remains
    a separate runtime gate; this is a narrow delimiter check, not a SQL parser.
    """
    source = (SQL / "grants_runtime.sql").read_text()
    conditions = source.split("IF typ.oid IS NULL")[1:]
    assert len(conditions) == 2, "both preflight and postflight must be checked"
    token = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\bTHEN\b|[()]")
    for condition in conditions:
        depth = 0
        for match in token.finditer(condition):
            value = match.group()
            if value == "(":
                depth += 1
            elif value == ")":
                depth -= 1
                assert depth >= 0
            elif value == "THEN" and depth == 0:
                assert (
                    condition[match.end() :]
                    .lstrip()
                    .startswith(
                        "RAISE EXCEPTION USING ERRCODE='PZ011',MESSAGE='Events type topology mismatch'"
                    )
                ), "SQL CASE prematurely terminates the PL/pgSQL IF expression"
                break
        else:
            raise AssertionError("type topology IF has no top-level THEN")
