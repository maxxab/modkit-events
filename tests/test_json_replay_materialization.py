"""Source guards for one bounded replay materialization, not SQL execution.

Actual byte semantics and representation cost require the separately reviewed
PostgreSQL checks. These guards catch accidental removal or unsafe placement of
the outer materialization without replacing the canonical parser in Python.
"""

from importlib.resources import files


def replay_function():
    source = files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()
    start = source.index("CREATE FUNCTION modkit_events._json_to_j(")
    end = source.index("$body$;", start)
    return " ".join(source[start:end].split())


def test_replay_size_gate_precedes_full_materialization():
    source = replay_function()
    copy = "p_raw := pg_catalog.substr(p_raw,1,n);"
    assert copy in source, "Replay bytes must be materialized once before scanning"
    null_guard = source.index("IF p_raw IS NULL THEN RETURN NULL; END IF;")
    length = source.index("n := pg_catalog.octet_length(p_raw);")
    size_guard = source.index("IF n > 1048576 THEN RETURN NULL; END IF;")
    assert null_guard < length < size_guard < source.index(copy)


def test_replay_retains_one_flat_input_for_complete_parse():
    source = replay_function()
    copy = "p_raw := pg_catalog.substr(p_raw,1,n);"
    assert source.count(copy) == 1, "Only the outer replay boundary materializes the input"
    utf8 = source.index("modkit_events._utf8_valid(p_raw,1048576,FALSE)")
    bom = source.index("pg_catalog.substr(p_raw,1,3) = pg_catalog.decode('efbbbf','hex')")
    start = source.index("pos := modkit_events._skip_json_ws(p_raw,0);")
    parse = source.index("result := modkit_events._json_value(p_raw,pos,0,262144);")
    complete = source.index(
        "IF result.value IS NULL OR modkit_events._skip_json_ws(p_raw,result.after_pos)"
        " <> pg_catalog.octet_length(p_raw) THEN RETURN NULL; END IF;"
    )
    assert source.index(copy) < utf8 < bom < start < parse < complete
    assert source.index("RETURN result.value;") > complete
