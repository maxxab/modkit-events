-- NEW initial schema SOURCE IN PROGRESS. NOT READY TO APPLY.
-- Partial private validators and core records; public functions/grants still pending.
-- Bounded SQL checks do not qualify this complete migration. Application owns transaction.
-- Source-only installation preflight. Application must already own the explicit
-- component transaction and have selected the authorized existing owner role.
-- This block creates/modifies no role, membership, default ACL or transaction.
DO $preflight$
DECLARE
    owner_oid pg_catalog.oid;
    runtime_oid pg_catalog.oid;
    reconciler_oid pg_catalog.oid;
    operator_oid pg_catalog.oid;
BEGIN
    IF pg_catalog.current_setting('server_version_num')::pg_catalog.int4 < 160000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ011',MESSAGE='unsupported installation profile';
    END IF;
    SELECT r.oid INTO owner_oid FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = CURRENT_USER AND NOT r.rolcanlogin AND NOT r.rolsuper
        AND NOT r.rolbypassrls AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication;
    SELECT r.oid INTO runtime_oid FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = 'modkit_runtime' AND NOT r.rolcanlogin AND NOT r.rolsuper
        AND NOT r.rolbypassrls AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication;
    SELECT r.oid INTO reconciler_oid FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = 'modkit_reconciler' AND NOT r.rolcanlogin AND NOT r.rolsuper
        AND NOT r.rolbypassrls AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication;
    SELECT r.oid INTO operator_oid FROM pg_catalog.pg_roles AS r
      WHERE r.rolname = 'modkit_operator' AND NOT r.rolcanlogin AND NOT r.rolsuper
        AND NOT r.rolbypassrls AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT r.rolreplication;
    IF owner_oid IS NULL OR runtime_oid IS NULL OR reconciler_oid IS NULL OR operator_oid IS NULL
       OR owner_oid IN (runtime_oid,reconciler_oid,operator_oid)
       OR NOT pg_catalog.has_database_privilege(owner_oid,pg_catalog.current_database(),'CREATE')
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_namespace AS n WHERE n.nspname='modkit_events') THEN
        RAISE EXCEPTION USING ERRCODE='PZ011',MESSAGE='invalid installation ownership or target';
    END IF;
    -- Conservative fail-closed ancestry: owner/operator have no other parent
    -- roles; runtime/reconciler may inherit only the operator read subset.
    -- Inherit/set-option flags do not waive inspection of an existing chain.
    IF EXISTS (
        WITH RECURSIVE ancestry(origin,ancestor) AS (
            SELECT seeds.id,seeds.id FROM (VALUES(owner_oid),(runtime_oid),(reconciler_oid),(operator_oid)) AS seeds(id)
            UNION
            SELECT a.origin,m.roleid FROM ancestry AS a
              JOIN pg_catalog.pg_auth_members AS m ON m.member=a.ancestor
        )
        SELECT 1 FROM ancestry AS a
        WHERE a.ancestor <> a.origin
          AND NOT (a.origin IN (runtime_oid,reconciler_oid) AND a.ancestor=operator_oid)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='PZ011',MESSAGE='unsafe installation role ancestry';
    END IF;
END
$preflight$;
CREATE SCHEMA modkit_events;
REVOKE ALL ON SCHEMA modkit_events FROM PUBLIC;

CREATE FUNCTION modkit_events._utf8_valid(
    p_raw pg_catalog.bytea,
    p_max_bytes pg_catalog.int4,
    p_nonblank pg_catalog.bool
) RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    i pg_catalog.int4 := 0;
    lead pg_catalog.int4;
    continuation pg_catalog.int4;
    width pg_catalog.int4;
    cp pg_catalog.int4;
    j pg_catalog.int4;
    seen_nonblank pg_catalog.bool := FALSE;
BEGIN
    IF p_raw IS NULL OR p_max_bytes IS NULL OR p_nonblank IS NULL
       OR p_max_bytes < 0 OR p_max_bytes > 1048576 THEN
        RETURN FALSE;
    END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n > p_max_bytes THEN RETURN FALSE; END IF;
    WHILE i < n LOOP
        lead := pg_catalog.get_byte(p_raw, i);
        IF lead <= 127 THEN
            width := 1; cp := lead;
        ELSIF lead BETWEEN 194 AND 223 THEN
            width := 2; cp := lead - 192;
        ELSIF lead BETWEEN 224 AND 239 THEN
            width := 3; cp := lead - 224;
        ELSIF lead BETWEEN 240 AND 244 THEN
            width := 4; cp := lead - 240;
        ELSE RETURN FALSE;
        END IF;
        IF width > n - i THEN RETURN FALSE; END IF;
        j := 1;
        WHILE j < width LOOP
            continuation := pg_catalog.get_byte(p_raw, i + j);
            IF continuation < 128 OR continuation > 191 THEN RETURN FALSE; END IF;
            cp := cp * 64 + continuation - 128;
            j := j + 1;
        END LOOP;
        IF (width = 2 AND cp < 128) OR (width = 3 AND cp < 2048)
           OR (width = 4 AND cp < 65536) OR cp BETWEEN 55296 AND 57343
           OR cp > 1114111 THEN
            RETURN FALSE;
        END IF;
        IF NOT (cp BETWEEN 9 AND 13 OR cp BETWEEN 28 AND 32 OR cp = 133
                OR cp = 160 OR cp = 5760 OR cp BETWEEN 8192 AND 8202
                OR cp = 8232 OR cp = 8233 OR cp = 8239 OR cp = 8287 OR cp = 12288) THEN
            seen_nonblank := TRUE;
        END IF;
        i := i + width;
    END LOOP;
    RETURN NOT p_nonblank OR seen_nonblank;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._utf8_valid(pg_catalog.bytea,pg_catalog.int4,pg_catalog.bool) FROM PUBLIC;

CREATE FUNCTION modkit_events._bounded_uint(
    p_raw pg_catalog.bytea,
    p_offset pg_catalog.int4,
    p_width pg_catalog.int4,
    p_max pg_catalog.int4
) RETURNS pg_catalog.int4
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    result pg_catalog.int4 := 0;
    value pg_catalog.int4;
    j pg_catalog.int4 := 0;
BEGIN
    IF p_raw IS NULL OR p_offset IS NULL OR p_width IS NULL OR p_max IS NULL
       OR p_offset < 0 OR p_width < 1 OR p_width > 8 OR p_max < 0 OR p_max > 1048576 THEN
        RETURN NULL;
    END IF;
    n := pg_catalog.octet_length(p_raw);
    IF p_offset > n OR p_width > n - p_offset THEN RETURN NULL; END IF;
    WHILE j < p_width LOOP
        value := pg_catalog.get_byte(p_raw,p_offset+j);
        -- Guard BEFORE multiplication; never accumulate an attacker uint64.
        IF result > p_max / 256 OR (result = p_max / 256 AND value > p_max % 256) THEN
            RETURN NULL;
        END IF;
        result := result * 256 + value;
        j := j + 1;
    END LOOP;
    RETURN result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._bounded_uint(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._scope_valid(
    p_frame pg_catalog.bytea,
    p_application pg_catalog.bytea,
    p_tenant pg_catalog.bytea,
    p_owner pg_catalog.bytea
) RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4 := 5;
    size pg_catalog.int4;
    marker pg_catalog.int4;
    field_index pg_catalog.int4;
    expected pg_catalog.bytea[];
    value pg_catalog.bytea;
BEGIN
    IF p_frame IS NULL OR p_application IS NULL THEN RETURN FALSE; END IF;
    n := pg_catalog.octet_length(p_frame);
    IF n < 10 OR n > 781 OR pg_catalog.substr(p_frame,1,5) <> pg_catalog.decode('4d4b534301','hex') THEN RETURN FALSE; END IF;
    IF NOT modkit_events._utf8_valid(p_application,256,TRUE) THEN RETURN FALSE; END IF;
    size := modkit_events._bounded_uint(p_frame,pos,2,256);
    IF size IS NULL OR size = 0 THEN RETURN FALSE; END IF;
    pos := pos + 2;
    IF size > n - pos THEN RETURN FALSE; END IF;
    value := pg_catalog.substr(p_frame,pos+1,size);
    IF value IS DISTINCT FROM p_application THEN RETURN FALSE; END IF;
    pos := pos + size;
    expected := ARRAY[p_tenant,p_owner]::pg_catalog.bytea[];
    FOR field_index IN 1..2 LOOP
        IF pos >= n THEN RETURN FALSE; END IF;
        marker := pg_catalog.get_byte(p_frame,pos);
        pos := pos + 1;
        IF marker = 0 THEN
            IF expected[field_index] IS NOT NULL THEN RETURN FALSE; END IF;
        ELSIF marker = 1 THEN
            IF expected[field_index] IS NULL OR NOT modkit_events._utf8_valid(expected[field_index],256,TRUE) THEN RETURN FALSE; END IF;
            size := modkit_events._bounded_uint(p_frame,pos,2,256);
            IF size IS NULL OR size = 0 THEN RETURN FALSE; END IF;
            pos := pos + 2;
            IF size > n - pos THEN RETURN FALSE; END IF;
            value := pg_catalog.substr(p_frame,pos+1,size);
            IF value IS DISTINCT FROM expected[field_index] THEN RETURN FALSE; END IF;
            pos := pos + size;
        ELSE RETURN FALSE;
        END IF;
    END LOOP;
    RETURN pos = n;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._scope_valid(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._record_fields(
    p_raw pg_catalog.bytea,
    p_tag pg_catalog.bytea,
    p_count pg_catalog.int4
) RETURNS pg_catalog.bytea[]
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4 := 5;
    size pg_catalog.int4;
    count_value pg_catalog.int4;
    index_value pg_catalog.int4 := 0;
    result pg_catalog.bytea[] := ARRAY[]::pg_catalog.bytea[];
BEGIN
    IF p_raw IS NULL OR p_tag IS NULL OR p_count IS NULL OR p_count < 0 OR p_count > 32 THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n < 17 OR n > 1048576 OR pg_catalog.substr(p_raw,1,5) <> pg_catalog.decode('4d4b504601','hex') THEN RETURN NULL; END IF;
    size := modkit_events._bounded_uint(p_raw,pos,8,1048576);
    IF size IS NULL THEN RETURN NULL; END IF;
    pos := pos + 8;
    IF size > n - pos OR pg_catalog.substr(p_raw,pos+1,size) IS DISTINCT FROM p_tag THEN RETURN NULL; END IF;
    pos := pos + size;
    count_value := modkit_events._bounded_uint(p_raw,pos,4,32);
    IF count_value IS DISTINCT FROM p_count THEN RETURN NULL; END IF;
    pos := pos + 4;
    WHILE index_value < p_count LOOP
        size := modkit_events._bounded_uint(p_raw,pos,8,1048576);
        IF size IS NULL THEN RETURN NULL; END IF;
        pos := pos + 8;
        IF size > n - pos THEN RETURN NULL; END IF;
        result := pg_catalog.array_append(result,pg_catalog.substr(p_raw,pos+1,size));
        pos := pos + size;
        index_value := index_value + 1;
    END LOOP;
    IF pos <> n THEN RETURN NULL; END IF;
    RETURN result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._record_fields(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._decimal_valid(
    p_raw pg_catalog.bytea,
    p_signed pg_catalog.bool
) RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4 := 0;
    negative pg_catalog.bool := FALSE;
    digit pg_catalog.int4;
BEGIN
    IF p_raw IS NULL OR p_signed IS NULL THEN RETURN FALSE; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n = 0 OR n > 4097 THEN RETURN FALSE; END IF;
    IF pg_catalog.get_byte(p_raw,0) = 45 THEN
        IF NOT p_signed THEN RETURN FALSE; END IF;
        negative := TRUE; pos := 1;
    END IF;
    IF n - pos < 1 OR n - pos > 4096 THEN RETURN FALSE; END IF;
    IF pg_catalog.get_byte(p_raw,pos) = 48 THEN
        -- Signed J integers allow canonical0; positive versions do not.
        RETURN p_signed AND NOT negative AND n - pos = 1;
    END IF;
    WHILE pos < n LOOP
        digit := pg_catalog.get_byte(p_raw,pos);
        IF digit < 48 OR digit > 57 THEN RETURN FALSE; END IF;
        pos := pos + 1;
    END LOOP;
    RETURN TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._decimal_valid(pg_catalog.bytea,pg_catalog.bool) FROM PUBLIC;

CREATE FUNCTION modkit_events._float_hex_valid(p_raw pg_catalog.bytea)
RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    raw pg_catalog.bytea;
    n pg_catalog.int4;
    i pg_catalog.int4;
    digit pg_catalog.int4;
    exponent_value pg_catalog.int4 := 0;
    exponent_negative pg_catalog.bool;
    fraction_nonzero pg_catalog.bool := FALSE;
    subnormal pg_catalog.bool;
BEGIN
    IF p_raw IS NULL THEN RETURN FALSE; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n < 8 OR n > 24 THEN RETURN FALSE; END IF;
    raw := p_raw;
    IF pg_catalog.get_byte(raw,0) = 45 THEN
        raw := pg_catalog.substr(raw,2,n-1);
        n := n - 1;
    END IF;
    IF raw = pg_catalog.decode('3078302e30702b30','hex') THEN RETURN TRUE; END IF;
    IF n < 20 OR n > 23 THEN RETURN FALSE; END IF;
    IF pg_catalog.substr(raw,1,4) = pg_catalog.decode('3078302e','hex') THEN
        subnormal := TRUE;
    ELSIF pg_catalog.substr(raw,1,4) = pg_catalog.decode('3078312e','hex') THEN
        subnormal := FALSE;
    ELSE RETURN FALSE;
    END IF;
    FOR i IN 4..16 LOOP
        digit := pg_catalog.get_byte(raw,i);
        IF NOT (digit BETWEEN 48 AND 57 OR digit BETWEEN 97 AND 102) THEN RETURN FALSE; END IF;
        IF digit <> 48 THEN fraction_nonzero := TRUE; END IF;
    END LOOP;
    IF pg_catalog.get_byte(raw,17) <> 112 THEN RETURN FALSE; END IF;
    digit := pg_catalog.get_byte(raw,18);
    IF digit <> 43 AND digit <> 45 THEN RETURN FALSE; END IF;
    exponent_negative := digit = 45;
    IF n > 20 AND pg_catalog.get_byte(raw,19) = 48 THEN RETURN FALSE; END IF;
    FOR i IN 19..n-1 LOOP
        digit := pg_catalog.get_byte(raw,i);
        IF digit < 48 OR digit > 57 THEN RETURN FALSE; END IF;
        exponent_value := exponent_value * 10 + digit - 48;
    END LOOP;
    IF exponent_negative THEN
        IF exponent_value = 0 OR exponent_value > 1022 THEN RETURN FALSE; END IF;
    ELSIF exponent_value > 1023 THEN RETURN FALSE;
    END IF;
    IF subnormal THEN RETURN fraction_nonzero AND exponent_negative AND exponent_value = 1022; END IF;
    RETURN TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._float_hex_valid(pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._j_nodes(
    p_raw pg_catalog.bytea,
    p_depth pg_catalog.int4,
    p_budget pg_catalog.int4
) RETURNS pg_catalog.int4
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    tag pg_catalog.int4;
    size pg_catalog.int4;
    count_value pg_catalog.int4;
    pos pg_catalog.int4;
    index_value pg_catalog.int4 := 0;
    nodes pg_catalog.int4 := 1;
    child_nodes pg_catalog.int4;
    value pg_catalog.bytea;
    key_value pg_catalog.bytea;
    previous_key pg_catalog.bytea;
BEGIN
    IF p_raw IS NULL OR p_depth IS NULL OR p_budget IS NULL
       OR p_depth < 0 OR p_depth > 32 OR p_budget < 1 OR p_budget > 262144 THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n < 1 OR n > 1048576 THEN RETURN NULL; END IF;
    tag := pg_catalog.get_byte(p_raw,0);
    IF tag IN (110,116,102) THEN
        IF n = 1 THEN RETURN 1; ELSE RETURN NULL; END IF;
    ELSIF tag IN (105,100,115) THEN
        size := modkit_events._bounded_uint(p_raw,1,8,1048576);
        IF size IS NULL OR size <> n - 9 THEN RETURN NULL; END IF;
        value := pg_catalog.substr(p_raw,10,size);
        IF (tag = 105 AND modkit_events._decimal_valid(value,TRUE))
           OR (tag = 100 AND modkit_events._float_hex_valid(value))
           OR (tag = 115 AND modkit_events._utf8_valid(value,1048576,FALSE)) THEN RETURN 1;
        ELSE RETURN NULL;
        END IF;
    ELSIF tag NOT IN (97,111) THEN RETURN NULL;
    END IF;
    count_value := modkit_events._bounded_uint(p_raw,1,4,65536);
    IF count_value IS NULL THEN RETURN NULL; END IF;
    pos := 5;
    WHILE index_value < count_value LOOP
        IF nodes >= p_budget THEN RETURN NULL; END IF;
        IF tag = 111 THEN
            size := modkit_events._bounded_uint(p_raw,pos,8,1048576);
            IF size IS NULL THEN RETURN NULL; END IF;
            pos := pos + 8;
            IF size > n - pos THEN RETURN NULL; END IF;
            key_value := pg_catalog.substr(p_raw,pos+1,size);
            IF NOT modkit_events._utf8_valid(key_value,1048576,FALSE)
               OR (previous_key IS NOT NULL AND previous_key >= key_value) THEN RETURN NULL; END IF;
            previous_key := key_value;
            pos := pos + size;
        END IF;
        size := modkit_events._bounded_uint(p_raw,pos,8,1048576);
        IF size IS NULL OR size = 0 THEN RETURN NULL; END IF;
        pos := pos + 8;
        IF size > n - pos THEN RETURN NULL; END IF;
        value := pg_catalog.substr(p_raw,pos+1,size);
        child_nodes := modkit_events._j_nodes(value,p_depth+1,p_budget-nodes);
        IF child_nodes IS NULL THEN RETURN NULL; END IF;
        nodes := nodes + child_nodes;
        pos := pos + size;
        index_value := index_value + 1;
    END LOOP;
    IF pos <> n THEN RETURN NULL; END IF;
    RETURN nodes;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._j_nodes(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._integer_power(p_base pg_catalog.int4,p_exponent pg_catalog.int4)
RETURNS pg_catalog.numeric
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    base_value pg_catalog.numeric;
    result pg_catalog.numeric := 1;
    exponent_value pg_catalog.int4;
BEGIN
    IF p_base IS NULL OR p_exponent IS NULL OR p_base NOT IN (2,10) OR p_exponent < 0 OR p_exponent > 4421 THEN RETURN NULL; END IF;
    base_value := p_base::pg_catalog.numeric;
    exponent_value := p_exponent;
    WHILE exponent_value > 0 LOOP
        IF exponent_value % 2 = 1 THEN result := result * base_value; END IF;
        exponent_value := exponent_value / 2;
        IF exponent_value > 0 THEN base_value := base_value * base_value; END IF;
    END LOOP;
    RETURN result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._integer_power(pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._hex_fraction(p_fraction pg_catalog.numeric)
RETURNS pg_catalog.text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    remaining pg_catalog.numeric := p_fraction;
    result pg_catalog.text := '';
    digit pg_catalog.int4;
    i pg_catalog.int4;
BEGIN
    IF p_fraction IS NULL OR p_fraction < 0 OR p_fraction >= 4503599627370496::pg_catalog.numeric
       OR pg_catalog.trunc(p_fraction) <> p_fraction THEN RETURN NULL; END IF;
    FOR i IN 1..13 LOOP
        digit := pg_catalog.mod(remaining,16::pg_catalog.numeric)::pg_catalog.int4;
        result := pg_catalog.substr('0123456789abcdef',digit+1,1) || result;
        remaining := pg_catalog.div(remaining,16::pg_catalog.numeric);
    END LOOP;
    RETURN result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._hex_fraction(pg_catalog.numeric) FROM PUBLIC;

CREATE FUNCTION modkit_events._decimal_float_hex(p_raw pg_catalog.bytea)
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4 := 0;
    digit pg_catalog.int4;
    negative pg_catalog.bool := FALSE;
    fractional pg_catalog.bool := FALSE;
    has_float_marker pg_catalog.bool := FALSE;
    exponent_negative pg_catalog.bool := FALSE;
    total_digits pg_catalog.int4 := 0;
    significant_digits pg_catalog.int4 := 0;
    fraction_digits pg_catalog.int4 := 0;
    exponent_digits pg_catalog.int4 := 0;
    exponent_value pg_catalog.int4 := 0;
    decimal_order pg_catalog.int4;
    mantissa pg_catalog.numeric := 0;
    numerator pg_catalog.numeric;
    denominator pg_catalog.numeric := 1;
    scaled_n pg_catalog.numeric;
    scaled_d pg_catalog.numeric;
    quotient pg_catalog.numeric;
    remainder_value pg_catalog.numeric;
    binary_exponent pg_catalog.int4 := 0;
    shift_value pg_catalog.int4;
    sign_text pg_catalog.text := '';
    result pg_catalog.text;
BEGIN
    IF p_raw IS NULL THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n < 1 OR n > 8192 THEN RETURN NULL; END IF;
    IF pg_catalog.get_byte(p_raw,0) = 45 THEN
        negative := TRUE; sign_text := '-'; pos := 1;
    END IF;
    IF pos >= n THEN RETURN NULL; END IF;
    digit := pg_catalog.get_byte(p_raw,pos);
    IF digit < 48 OR digit > 57 THEN RETURN NULL; END IF;
    IF digit = 48 AND pos+1 < n AND pg_catalog.get_byte(p_raw,pos+1) BETWEEN 48 AND 57 THEN RETURN NULL; END IF;
    -- Parse integer and optional fractional digits without decimal/float casts.
    LOOP
        IF pos >= n THEN EXIT; END IF;
        digit := pg_catalog.get_byte(p_raw,pos);
        IF digit BETWEEN 48 AND 57 THEN
            total_digits := total_digits + 1;
            IF total_digits > 4096 THEN RETURN NULL; END IF;
            mantissa := mantissa * 10::pg_catalog.numeric + (digit-48)::pg_catalog.numeric;
            IF mantissa <> 0 OR significant_digits > 0 THEN significant_digits := significant_digits + 1; END IF;
            IF fractional THEN fraction_digits := fraction_digits + 1; END IF;
            pos := pos + 1;
        ELSIF digit = 46 AND NOT fractional THEN
            fractional := TRUE; has_float_marker := TRUE; pos := pos + 1;
            IF pos >= n OR pg_catalog.get_byte(p_raw,pos) NOT BETWEEN 48 AND 57 THEN RETURN NULL; END IF;
        ELSE EXIT;
        END IF;
    END LOOP;
    IF pos < n AND pg_catalog.get_byte(p_raw,pos) IN (69,101) THEN
        has_float_marker := TRUE; pos := pos + 1;
        IF pos < n AND pg_catalog.get_byte(p_raw,pos) IN (43,45) THEN
            exponent_negative := pg_catalog.get_byte(p_raw,pos) = 45;
            pos := pos + 1;
        END IF;
        WHILE pos < n LOOP
            digit := pg_catalog.get_byte(p_raw,pos);
            IF digit < 48 OR digit > 57 THEN RETURN NULL; END IF;
            exponent_digits := exponent_digits + 1;
            IF exponent_digits > 6 THEN RETURN NULL; END IF;
            exponent_value := exponent_value * 10 + digit - 48;
            pos := pos + 1;
        END LOOP;
        IF exponent_digits = 0 THEN RETURN NULL; END IF;
    END IF;
    IF pos <> n OR NOT has_float_marker THEN RETURN NULL; END IF;
    IF mantissa = 0 THEN RETURN pg_catalog.convert_to(sign_text || '0x0.0p+0','UTF8'); END IF;
    IF exponent_negative THEN exponent_value := -exponent_value; END IF;
    exponent_value := exponent_value - fraction_digits;
    decimal_order := significant_digits + exponent_value - 1;
    IF decimal_order > 309 THEN RETURN NULL; END IF;
    IF decimal_order < -325 THEN RETURN pg_catalog.convert_to(sign_text || '0x0.0p+0','UTF8'); END IF;
    numerator := mantissa;
    IF exponent_value >= 0 THEN
        numerator := numerator * modkit_events._integer_power(10,exponent_value);
    ELSE denominator := modkit_events._integer_power(10,-exponent_value);
    END IF;
    IF numerator IS NULL OR denominator IS NULL THEN RETURN NULL; END IF;
    scaled_n := numerator; scaled_d := denominator;
    IF scaled_n >= scaled_d THEN
        WHILE scaled_n >= scaled_d * 2::pg_catalog.numeric LOOP
            scaled_d := scaled_d * 2::pg_catalog.numeric;
            binary_exponent := binary_exponent + 1;
            IF binary_exponent > 1023 THEN RETURN NULL; END IF;
        END LOOP;
    ELSE
        WHILE scaled_n < scaled_d LOOP
            scaled_n := scaled_n * 2::pg_catalog.numeric;
            binary_exponent := binary_exponent - 1;
            IF binary_exponent < -1075 THEN RETURN pg_catalog.convert_to(sign_text || '0x0.0p+0','UTF8'); END IF;
        END LOOP;
    END IF;
    IF binary_exponent < -1022 THEN shift_value := 1074;
    ELSE shift_value := 52 - binary_exponent;
    END IF;
    scaled_n := numerator; scaled_d := denominator;
    IF shift_value >= 0 THEN scaled_n := scaled_n * modkit_events._integer_power(2,shift_value);
    ELSE scaled_d := scaled_d * modkit_events._integer_power(2,-shift_value);
    END IF;
    quotient := pg_catalog.div(scaled_n,scaled_d);
    remainder_value := pg_catalog.mod(scaled_n,scaled_d);
    IF remainder_value * 2::pg_catalog.numeric > scaled_d OR
       (remainder_value * 2::pg_catalog.numeric = scaled_d AND pg_catalog.mod(quotient,2::pg_catalog.numeric) = 1) THEN
        quotient := quotient + 1;
    END IF;
    IF quotient = 0 THEN RETURN pg_catalog.convert_to(sign_text || '0x0.0p+0','UTF8'); END IF;
    IF binary_exponent < -1022 AND quotient < 4503599627370496::pg_catalog.numeric THEN
        result := sign_text || '0x0.' || modkit_events._hex_fraction(quotient) || 'p-1022';
    ELSE
        IF binary_exponent < -1022 THEN binary_exponent := -1022; END IF;
        IF quotient = 9007199254740992::pg_catalog.numeric THEN
            quotient := 4503599627370496::pg_catalog.numeric;
            binary_exponent := binary_exponent + 1;
        END IF;
        IF binary_exponent > 1023 THEN RETURN NULL; END IF;
        result := sign_text || '0x1.' || modkit_events._hex_fraction(quotient - 4503599627370496::pg_catalog.numeric) || 'p';
        IF binary_exponent >= 0 THEN result := result || '+'; END IF;
        result := result || binary_exponent::pg_catalog.text;
    END IF;
    RETURN pg_catalog.convert_to(result,'UTF8');
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._decimal_float_hex(pg_catalog.bytea) FROM PUBLIC;

CREATE TYPE modkit_events._parse_result AS (
    value pg_catalog.bytea,
    after_pos pg_catalog.int4,
    nodes pg_catalog.int4
);
REVOKE ALL ON TYPE modkit_events._parse_result FROM PUBLIC;

CREATE FUNCTION modkit_events._hex4(p_raw pg_catalog.bytea,p_pos pg_catalog.int4)
RETURNS pg_catalog.int4
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    i pg_catalog.int4;
    digit pg_catalog.int4;
    result pg_catalog.int4 := 0;
BEGIN
    IF p_raw IS NULL OR p_pos IS NULL OR p_pos < 0 OR p_pos > pg_catalog.octet_length(p_raw)-4 THEN RETURN NULL; END IF;
    FOR i IN 0..3 LOOP
        digit := pg_catalog.get_byte(p_raw,p_pos+i);
        IF digit BETWEEN 48 AND 57 THEN digit := digit-48;
        ELSIF digit BETWEEN 65 AND 70 THEN digit := digit-55;
        ELSIF digit BETWEEN 97 AND 102 THEN digit := digit-87;
        ELSE RETURN NULL;
        END IF;
        result := result * 16 + digit;
    END LOOP;
    RETURN result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._hex4(pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._utf8_scalar(p_cp pg_catalog.int4)
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE result pg_catalog.bytea;
BEGIN
    IF p_cp IS NULL OR p_cp < 0 OR p_cp > 1114111 OR p_cp BETWEEN 55296 AND 57343 THEN RETURN NULL; END IF;
    IF p_cp < 128 THEN RETURN pg_catalog.set_byte(pg_catalog.decode('00','hex'),0,p_cp);
    ELSIF p_cp < 2048 THEN
        result := pg_catalog.set_byte(pg_catalog.decode('0000','hex'),0,192+p_cp/64);
        RETURN pg_catalog.set_byte(result,1,128+p_cp%64);
    ELSIF p_cp < 65536 THEN
        result := pg_catalog.set_byte(pg_catalog.decode('000000','hex'),0,224+p_cp/4096);
        result := pg_catalog.set_byte(result,1,128+(p_cp/64)%64);
        RETURN pg_catalog.set_byte(result,2,128+p_cp%64);
    ELSE
        result := pg_catalog.set_byte(pg_catalog.decode('00000000','hex'),0,240+p_cp/262144);
        result := pg_catalog.set_byte(result,1,128+(p_cp/4096)%64);
        result := pg_catalog.set_byte(result,2,128+(p_cp/64)%64);
        RETURN pg_catalog.set_byte(result,3,128+p_cp%64);
    END IF;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._utf8_scalar(pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._json_string_chunks(p_raw pg_catalog.bytea,p_offset pg_catalog.int4)
RETURNS TABLE (chunk pg_catalog.bytea, after_pos pg_catalog.int4)
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4;
    b pg_catalog.int4;
    cp pg_catalog.int4;
    low_cp pg_catalog.int4;
    output pg_catalog.bytea := pg_catalog.decode('','hex');
    piece pg_catalog.bytea;
    run_start pg_catalog.int4;
    total_size pg_catalog.int4 := 0;
BEGIN
    IF p_raw IS NULL OR p_offset IS NULL OR p_offset < 0 THEN RETURN; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n > 1048576 OR p_offset >= n OR pg_catalog.get_byte(p_raw,p_offset) <> 34 THEN RETURN; END IF;
    pos := p_offset+1;
    WHILE pos < n LOOP
        b := pg_catalog.get_byte(p_raw,pos);
        pos := pos+1;
        IF b = 34 THEN
            chunk := output; after_pos := pos; RETURN NEXT; RETURN;
        ELSIF b < 32 THEN RETURN;
        ELSIF b = 92 THEN
            IF pos >= n THEN RETURN; END IF;
            b := pg_catalog.get_byte(p_raw,pos); pos := pos+1;
            IF b IN (34,47,92) THEN piece := modkit_events._utf8_scalar(b);
            ELSIF b = 98 THEN piece := modkit_events._utf8_scalar(8);
            ELSIF b = 102 THEN piece := modkit_events._utf8_scalar(12);
            ELSIF b = 110 THEN piece := modkit_events._utf8_scalar(10);
            ELSIF b = 114 THEN piece := modkit_events._utf8_scalar(13);
            ELSIF b = 116 THEN piece := modkit_events._utf8_scalar(9);
            ELSIF b = 117 THEN
                cp := modkit_events._hex4(p_raw,pos);
                IF cp IS NULL THEN RETURN; END IF;
                pos := pos+4;
                IF cp BETWEEN 55296 AND 56319 THEN
                    IF n-pos < 6 OR pg_catalog.get_byte(p_raw,pos) <> 92 OR pg_catalog.get_byte(p_raw,pos+1) <> 117 THEN RETURN; END IF;
                    low_cp := modkit_events._hex4(p_raw,pos+2);
                    IF low_cp IS NULL OR low_cp < 56320 OR low_cp > 57343 THEN RETURN; END IF;
                    cp := 65536+(cp-55296)*1024+(low_cp-56320);
                    pos := pos+6;
                ELSIF cp BETWEEN 56320 AND 57343 THEN RETURN;
                END IF;
                piece := modkit_events._utf8_scalar(cp);
            ELSE RETURN;
            END IF;
        ELSE
            run_start := pos-1;
            WHILE pos < n AND pos-run_start < 4096 LOOP
                b := pg_catalog.get_byte(p_raw,pos);
                IF b < 32 OR b IN (34,92) THEN EXIT; END IF;
                pos := pos+1;
            END LOOP;
            piece := pg_catalog.substr(p_raw,run_start+1,pos-run_start);
        END IF;
        IF piece IS NULL OR pg_catalog.octet_length(piece) > 1048576-total_size THEN RETURN; END IF;
        total_size := total_size+pg_catalog.octet_length(piece);
        IF pg_catalog.octet_length(output)+pg_catalog.octet_length(piece) > 4096 THEN
            chunk := output; after_pos := NULL; RETURN NEXT;
            output := ''::pg_catalog.bytea;
        END IF;
        output := output || piece; -- growing buffer bounded4096, never whole string
    END LOOP;
    RETURN;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._json_string_chunks(pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._json_string(p_raw pg_catalog.bytea,p_offset pg_catalog.int4)
RETURNS modkit_events._parse_result
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE output pg_catalog.bytea; end_pos pg_catalog.int4; markers pg_catalog.int8;
BEGIN
    SELECT pg_catalog.string_agg(c.chunk,''::pg_catalog.bytea ORDER BY c.ordinal),
           pg_catalog.max(c.after_pos),pg_catalog.count(c.after_pos)
      INTO output,end_pos,markers
      FROM modkit_events._json_string_chunks(p_raw,p_offset) WITH ORDINALITY AS c(chunk,after_pos,ordinal);
    IF markers <> 1 OR output IS NULL OR NOT modkit_events._utf8_valid(output,1048576,FALSE) THEN RETURN NULL; END IF;
    RETURN (output,end_pos,0)::modkit_events._parse_result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._json_string(pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._skip_json_ws(p_raw pg_catalog.bytea,p_offset pg_catalog.int4)
RETURNS pg_catalog.int4
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE pos pg_catalog.int4 := p_offset; n pg_catalog.int4;
BEGIN
    IF p_raw IS NULL OR p_offset IS NULL OR p_offset < 0 THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n > 1048576 OR pos > n THEN RETURN NULL; END IF;
    WHILE pos < n LOOP
        IF pg_catalog.get_byte(p_raw,pos) NOT IN (9,10,13,32) THEN EXIT; END IF;
        pos := pos+1;
    END LOOP;
    RETURN pos;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._skip_json_ws(pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._json_children(
    p_raw pg_catalog.bytea,p_offset pg_catalog.int4,p_depth pg_catalog.int4,p_budget pg_catalog.int4
) RETURNS TABLE (piece pg_catalog.bytea, sort_key pg_catalog.bytea, ordinal pg_catalog.int4,
                 after_pos pg_catalog.int4, node_count pg_catalog.int4)
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE n pg_catalog.int4; pos pg_catalog.int4; tag pg_catalog.int4; c pg_catalog.int4;
    is_object pg_catalog.bool; count_value pg_catalog.int4 := 0; nodes pg_catalog.int4 := 1;
    canonical_size pg_catalog.int4 := 5; child modkit_events._parse_result; key_result modkit_events._parse_result;
BEGIN
    IF p_raw IS NULL OR p_offset IS NULL OR p_depth IS NULL OR p_budget IS NULL
       OR p_offset < 0 OR p_depth < 0 OR p_depth > 32 OR p_budget < 1 OR p_budget > 262144 THEN RETURN; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n > 1048576 OR p_offset >= n THEN RETURN; END IF;
    tag := pg_catalog.get_byte(p_raw,p_offset);
    IF tag NOT IN (91,123) THEN RETURN; END IF;
    is_object := tag = 123;
    pos := modkit_events._skip_json_ws(p_raw,p_offset+1);
    IF pos >= n THEN RETURN; END IF;
    IF (is_object AND pg_catalog.get_byte(p_raw,pos) = 125) OR
       (NOT is_object AND pg_catalog.get_byte(p_raw,pos) = 93) THEN
        piece := NULL; sort_key := NULL; ordinal := 0; after_pos := pos+1; node_count := 1; RETURN NEXT; RETURN;
    END IF;
    LOOP
        count_value := count_value+1;
        IF count_value > 65536 OR nodes >= p_budget THEN RETURN; END IF;
        IF is_object THEN
            key_result := modkit_events._json_string(p_raw,pos);
            IF key_result.value IS NULL THEN RETURN; END IF;
            pos := modkit_events._skip_json_ws(p_raw,key_result.after_pos);
            IF pos >= n OR pg_catalog.get_byte(p_raw,pos) <> 58 THEN RETURN; END IF;
            pos := modkit_events._skip_json_ws(p_raw,pos+1);
        END IF;
        child := modkit_events._json_value(p_raw,pos,p_depth+1,p_budget-nodes);
        IF child.value IS NULL OR child.after_pos <= pos THEN RETURN; END IF;
        nodes := nodes+child.nodes;
        IF is_object THEN
            canonical_size := canonical_size+16+pg_catalog.octet_length(key_result.value)+pg_catalog.octet_length(child.value);
            IF canonical_size > 1048576 THEN RETURN; END IF;
            sort_key := key_result.value;
            piece := pg_catalog.int8send(pg_catalog.octet_length(sort_key)::pg_catalog.int8)||sort_key
                  ||pg_catalog.int8send(pg_catalog.octet_length(child.value)::pg_catalog.int8)||child.value;
        ELSE
            canonical_size := canonical_size+8+pg_catalog.octet_length(child.value);
            IF canonical_size > 1048576 THEN RETURN; END IF;
            sort_key := NULL;
            piece := pg_catalog.int8send(pg_catalog.octet_length(child.value)::pg_catalog.int8)||child.value;
        END IF;
        ordinal := count_value; after_pos := NULL; node_count := NULL; RETURN NEXT;
        pos := modkit_events._skip_json_ws(p_raw,child.after_pos);
        IF pos >= n THEN RETURN; END IF;
        c := pg_catalog.get_byte(p_raw,pos);
        IF (is_object AND c = 125) OR (NOT is_object AND c = 93) THEN pos := pos+1; EXIT; END IF;
        IF c <> 44 THEN RETURN; END IF;
        pos := modkit_events._skip_json_ws(p_raw,pos+1);
        IF pos >= n THEN RETURN; END IF;
    END LOOP;
    piece := NULL; sort_key := NULL; ordinal := 0; after_pos := pos; node_count := nodes; RETURN NEXT;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._json_children(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._json_value(
    p_raw pg_catalog.bytea,p_offset pg_catalog.int4,p_depth pg_catalog.int4,p_budget pg_catalog.int4
) RETURNS modkit_events._parse_result
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4 := p_offset;
    start_pos pg_catalog.int4;
    tag pg_catalog.int4;
    c pg_catalog.int4;
    child modkit_events._parse_result;
    key_result modkit_events._parse_result;
    output pg_catalog.bytea := pg_catalog.decode('','hex');
    piece pg_catalog.bytea;
    token pg_catalog.bytea;
    has_float pg_catalog.bool := FALSE;
    is_object pg_catalog.bool;
    count_value pg_catalog.int4 := 0;
    nodes pg_catalog.int4 := 1;
    markers pg_catalog.int8;
    distinct_keys pg_catalog.int8;
BEGIN
    IF p_raw IS NULL OR p_offset IS NULL OR p_depth IS NULL OR p_budget IS NULL
       OR p_offset < 0 OR p_depth < 0 OR p_depth > 32 OR p_budget < 1 OR p_budget > 262144 THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw);
    IF n > 1048576 OR pos >= n THEN RETURN NULL; END IF;
    tag := pg_catalog.get_byte(p_raw,pos);
    IF tag = 34 THEN
        child := modkit_events._json_string(p_raw,pos);
        IF child.value IS NULL OR pg_catalog.octet_length(child.value) > 1048567 THEN RETURN NULL; END IF;
        output := pg_catalog.decode('73','hex') || pg_catalog.int8send(pg_catalog.octet_length(child.value)::pg_catalog.int8) || child.value;
        RETURN (output,child.after_pos,1)::modkit_events._parse_result;
    ELSIF tag = 110 AND pg_catalog.substr(p_raw,pos+1,4) = pg_catalog.decode('6e756c6c','hex') THEN
        RETURN (pg_catalog.decode('6e','hex'),pos+4,1)::modkit_events._parse_result;
    ELSIF tag = 116 AND pg_catalog.substr(p_raw,pos+1,4) = pg_catalog.decode('74727565','hex') THEN
        RETURN (pg_catalog.decode('74','hex'),pos+4,1)::modkit_events._parse_result;
    ELSIF tag = 102 AND pg_catalog.substr(p_raw,pos+1,5) = pg_catalog.decode('66616c7365','hex') THEN
        RETURN (pg_catalog.decode('66','hex'),pos+5,1)::modkit_events._parse_result;
    ELSIF tag = 45 OR tag BETWEEN 48 AND 57 THEN
        start_pos := pos;
        WHILE pos < n LOOP
            c := pg_catalog.get_byte(p_raw,pos);
            IF NOT (c BETWEEN 48 AND 57 OR c IN (43,45,46,69,101)) THEN EXIT; END IF;
            IF c IN (46,69,101) THEN has_float := TRUE; END IF;
            pos := pos+1;
            IF pos-start_pos > 8192 THEN RETURN NULL; END IF;
        END LOOP;
        token := pg_catalog.substr(p_raw,start_pos+1,pos-start_pos);
        IF has_float THEN
            piece := modkit_events._decimal_float_hex(token);
            IF piece IS NULL THEN RETURN NULL; END IF;
            output := pg_catalog.decode('64','hex') || pg_catalog.int8send(pg_catalog.octet_length(piece)::pg_catalog.int8) || piece;
        ELSE
            IF token = pg_catalog.decode('2d30','hex') THEN token := pg_catalog.decode('30','hex'); END IF;
            IF NOT modkit_events._decimal_valid(token,TRUE) THEN RETURN NULL; END IF;
            output := pg_catalog.decode('69','hex') || pg_catalog.int8send(pg_catalog.octet_length(token)::pg_catalog.int8) || token;
        END IF;
        RETURN (output,pos,1)::modkit_events._parse_result;
    ELSIF tag NOT IN (91,123) THEN RETURN NULL;
    END IF;
    is_object := tag = 123;
    SELECT pg_catalog.string_agg(part.piece,''::pg_catalog.bytea ORDER BY part.sort_key,part.ordinal) FILTER (WHERE part.ordinal > 0),
           pg_catalog.count(*) FILTER (WHERE part.ordinal > 0),
           pg_catalog.count(DISTINCT part.sort_key) FILTER (WHERE part.ordinal > 0),
           pg_catalog.count(part.after_pos),pg_catalog.max(part.after_pos),pg_catalog.max(part.node_count)
      INTO output,count_value,distinct_keys,markers,pos,nodes
      FROM modkit_events._json_children(p_raw,p_offset,p_depth,p_budget) AS part;
    IF markers <> 1 OR (is_object AND distinct_keys <> count_value) THEN RETURN NULL; END IF;
    output := COALESCE(output,''::pg_catalog.bytea);
    IF is_object THEN output := pg_catalog.decode('6f','hex') || pg_catalog.int4send(count_value) || output;
    ELSE output := pg_catalog.decode('61','hex') || pg_catalog.int4send(count_value) || output;
    END IF;
    RETURN (output,pos,nodes)::modkit_events._parse_result;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._json_value(pg_catalog.bytea,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._json_to_j(p_raw pg_catalog.bytea)
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    result modkit_events._parse_result;
    pos pg_catalog.int4;
BEGIN
    IF p_raw IS NULL OR NOT modkit_events._utf8_valid(p_raw,1048576,FALSE)
       OR pg_catalog.substr(p_raw,1,3) = pg_catalog.decode('efbbbf','hex') THEN RETURN NULL; END IF;
    pos := modkit_events._skip_json_ws(p_raw,0);
    result := modkit_events._json_value(p_raw,pos,0,262144);
    IF result.value IS NULL OR modkit_events._skip_json_ws(p_raw,result.after_pos) <> pg_catalog.octet_length(p_raw) THEN RETURN NULL; END IF;
    RETURN result.value;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._json_to_j(pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._make_record(p_tag pg_catalog.bytea,p_fields pg_catalog.bytea[])
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    count_value pg_catalog.int4;
    field pg_catalog.bytea;
    output pg_catalog.bytea;
BEGIN
    IF p_tag IS NULL OR p_fields IS NULL OR pg_catalog.octet_length(p_tag) > 128 THEN RETURN NULL; END IF;
    count_value := pg_catalog.cardinality(p_fields);
    IF count_value > 32 OR (count_value > 0 AND (pg_catalog.array_ndims(p_fields) <> 1 OR pg_catalog.array_lower(p_fields,1) <> 1)) THEN RETURN NULL; END IF;
    output := pg_catalog.decode('4d4b504601','hex') || pg_catalog.int8send(pg_catalog.octet_length(p_tag)::pg_catalog.int8) || p_tag || pg_catalog.int4send(count_value);
    FOREACH field IN ARRAY p_fields LOOP
        IF field IS NULL OR pg_catalog.octet_length(field) > 1048576-8-pg_catalog.octet_length(output) THEN RETURN NULL; END IF;
        output := output || pg_catalog.int8send(pg_catalog.octet_length(field)::pg_catalog.int8) || field;
    END LOOP;
    RETURN output;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._make_record(pg_catalog.bytea,pg_catalog.bytea[]) FROM PUBLIC;

CREATE FUNCTION modkit_events._j_scalar_bytes(p_raw pg_catalog.bytea,p_tag pg_catalog.int4)
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE size pg_catalog.int4;
BEGIN
    IF p_raw IS NULL OR p_tag IS NULL OR pg_catalog.octet_length(p_raw) < 9 OR pg_catalog.get_byte(p_raw,0) <> p_tag THEN RETURN NULL; END IF;
    size := modkit_events._bounded_uint(p_raw,1,8,1048576);
    IF size IS NULL OR size <> pg_catalog.octet_length(p_raw)-9 THEN RETURN NULL; END IF;
    RETURN pg_catalog.substr(p_raw,10,size);
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._j_scalar_bytes(pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events._event_replay_frame(p_raw pg_catalog.bytea)
RETURNS pg_catalog.bytea
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    n pg_catalog.int4;
    pos pg_catalog.int4;
    count_value pg_catalog.int4 := 0;
    key_result modkit_events._parse_result;
    child modkit_events._parse_result;
    seen pg_catalog.bytea[] := ARRAY[]::pg_catalog.bytea[];
    event_id pg_catalog.bytea;
    event_name pg_catalog.bytea;
    version_value pg_catalog.bytea;
    payload pg_catalog.bytea;
    metadata pg_catalog.bytea;
    key_value pg_catalog.bytea;
    c pg_catalog.int4;
BEGIN
    IF p_raw IS NULL OR NOT modkit_events._utf8_valid(p_raw,1048576,FALSE)
       OR pg_catalog.substr(p_raw,1,3) = pg_catalog.decode('efbbbf','hex') THEN RETURN NULL; END IF;
    n := pg_catalog.octet_length(p_raw); pos := modkit_events._skip_json_ws(p_raw,0);
    IF pos >= n OR pg_catalog.get_byte(p_raw,pos) <> 123 THEN RETURN NULL; END IF;
    pos := modkit_events._skip_json_ws(p_raw,pos+1);
    LOOP
        count_value := count_value+1;
        IF count_value > 5 THEN RETURN NULL; END IF;
        key_result := modkit_events._json_string(p_raw,pos);
        IF key_result.value IS NULL OR pg_catalog.array_position(seen,key_result.value) IS NOT NULL THEN RETURN NULL; END IF;
        key_value := key_result.value; seen := pg_catalog.array_append(seen,key_value);
        pos := modkit_events._skip_json_ws(p_raw,key_result.after_pos);
        IF pos >= n OR pg_catalog.get_byte(p_raw,pos) <> 58 THEN RETURN NULL; END IF;
        pos := modkit_events._skip_json_ws(p_raw,pos+1);
        -- Envelope structure deliberately does not add a payload/metadata depth.
        child := modkit_events._json_value(p_raw,pos,0,262144);
        IF child.value IS NULL THEN RETURN NULL; END IF;
        IF key_value = pg_catalog.decode('6576656e745f6964','hex') THEN
            event_id := modkit_events._j_scalar_bytes(child.value,115);
            IF event_id IS NULL OR NOT modkit_events._utf8_valid(event_id,256,TRUE) THEN RETURN NULL; END IF;
        ELSIF key_value = pg_catalog.decode('6e616d65','hex') THEN
            event_name := modkit_events._j_scalar_bytes(child.value,115);
            IF event_name IS NULL OR NOT modkit_events._utf8_valid(event_name,256,TRUE) THEN RETURN NULL; END IF;
        ELSIF key_value = pg_catalog.decode('736368656d615f76657273696f6e','hex') THEN
            version_value := modkit_events._j_scalar_bytes(child.value,105);
            IF version_value IS NULL OR NOT modkit_events._decimal_valid(version_value,FALSE) THEN RETURN NULL; END IF;
        ELSIF key_value = pg_catalog.decode('7061796c6f6164','hex') THEN
            payload := child.value;
            IF pg_catalog.get_byte(payload,0) <> 111 THEN RETURN NULL; END IF;
        ELSIF key_value = pg_catalog.decode('6d65746164617461','hex') THEN
            metadata := child.value;
            IF pg_catalog.get_byte(metadata,0) <> 111 THEN RETURN NULL; END IF;
        ELSE RETURN NULL;
        END IF;
        pos := modkit_events._skip_json_ws(p_raw,child.after_pos);
        IF pos >= n THEN RETURN NULL; END IF;
        c := pg_catalog.get_byte(p_raw,pos);
        IF c = 125 THEN pos := pos+1; EXIT; END IF;
        IF c <> 44 THEN RETURN NULL; END IF;
        pos := modkit_events._skip_json_ws(p_raw,pos+1);
    END LOOP;
    IF count_value <> 5 OR modkit_events._skip_json_ws(p_raw,pos) <> n
       OR event_id IS NULL OR event_name IS NULL OR version_value IS NULL OR payload IS NULL OR metadata IS NULL THEN RETURN NULL; END IF;
    RETURN modkit_events._make_record(pg_catalog.decode('6576656e742d656e76656c6f7065','hex'),ARRAY[event_id,event_name,version_value,payload,metadata]::pg_catalog.bytea[]);
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._event_replay_frame(pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._optional_bytes(p_value pg_catalog.bytea)
RETURNS pg_catalog.bytea LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF p_value IS NULL THEN RETURN pg_catalog.decode('30','hex'); END IF;
    IF pg_catalog.octet_length(p_value) > 1048567 THEN RETURN NULL; END IF;
    RETURN pg_catalog.decode('31','hex') || pg_catalog.int8send(pg_catalog.octet_length(p_value)::pg_catalog.int8) || p_value;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._optional_bytes(pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._instant_bytes(p_value pg_catalog.timestamptz)
RETURNS pg_catalog.bytea LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE utc_value pg_catalog.timestamp;
BEGIN
    IF p_value IS NULL OR NOT pg_catalog.isfinite(p_value) THEN RETURN NULL; END IF;
    utc_value := pg_catalog.timezone('UTC'::pg_catalog.text,p_value);
    IF utc_value < '0001-01-01 00:00:00'::pg_catalog.timestamp
       OR utc_value >= '10000-01-01 00:00:00'::pg_catalog.timestamp THEN RETURN NULL; END IF;
    RETURN pg_catalog.convert_to(pg_catalog.to_char(utc_value,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'::pg_catalog.text),'UTF8');
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._instant_bytes(pg_catalog.timestamptz) FROM PUBLIC;

CREATE FUNCTION modkit_events._protected_valid(
    p_binding pg_catalog.bytea, p_state pg_catalog.text,
    p_sidecar pg_catalog.bytea, p_reference pg_catalog.bytea,
    p_codec pg_catalog.bytea, p_key_version pg_catalog.bytea,
    p_expiry pg_catalog.timestamptz, p_recovery pg_catalog.bytea,
    p_cleanup pg_catalog.text, p_projection pg_catalog.bytea)
RETURNS pg_catalog.bool LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE fields pg_catalog.bytea[]; item pg_catalog.bytea; expiry_bytes pg_catalog.bytea;
BEGIN
    IF p_binding IS NULL OR p_state IS NULL OR p_recovery IS NULL OR p_cleanup IS NULL OR p_projection IS NULL
       OR p_state NOT IN ('absent','present') OR p_cleanup NOT IN ('retain','erase_after_terminal') THEN RETURN FALSE; END IF;
    FOREACH item IN ARRAY ARRAY[p_binding,p_sidecar,p_reference,p_codec,p_key_version,p_recovery,p_projection]::pg_catalog.bytea[] LOOP
        IF item IS NOT NULL AND pg_catalog.octet_length(item) > 1048576 THEN RETURN FALSE; END IF;
    END LOOP;
    fields := modkit_events._record_fields(p_binding,pg_catalog.convert_to('protected-binding','UTF8'),10);
    IF fields IS NULL OR pg_catalog.octet_length(p_projection) = 0 THEN RETURN FALSE; END IF;
    IF pg_catalog.get_byte(p_projection,0) <> 111 OR modkit_events._j_nodes(p_projection,0,262144) IS NULL THEN RETURN FALSE; END IF;
    IF p_expiry IS NOT NULL THEN
        expiry_bytes := modkit_events._instant_bytes(p_expiry);
        IF expiry_bytes IS NULL THEN RETURN FALSE; END IF;
    END IF;
    IF p_state = 'absent' THEN
        IF p_sidecar IS NOT NULL OR p_reference IS NOT NULL OR p_codec IS NOT NULL OR p_key_version IS NOT NULL
           OR p_expiry IS NOT NULL OR p_cleanup <> 'retain' OR p_recovery <> ''::pg_catalog.bytea
           OR fields[8] <> ''::pg_catalog.bytea THEN RETURN FALSE; END IF;
    ELSE
        IF (p_sidecar IS NULL) = (p_reference IS NULL) OR p_codec IS NULL OR p_key_version IS NULL
           OR NOT modkit_events._utf8_valid(p_codec,256,TRUE) OR NOT modkit_events._utf8_valid(p_key_version,256,TRUE)
           OR pg_catalog.octet_length(fields[8]) = 0 OR pg_catalog.octet_length(p_recovery) = 0 THEN RETURN FALSE; END IF;
        IF (p_sidecar IS NOT NULL AND pg_catalog.octet_length(p_sidecar) = 0)
           OR (p_reference IS NOT NULL AND pg_catalog.octet_length(p_reference) = 0) THEN RETURN FALSE; END IF;
        IF pg_catalog.get_byte(p_recovery,0) <> 111 OR modkit_events._j_nodes(p_recovery,0,262144) IS NULL THEN RETURN FALSE; END IF;
    END IF;
    RETURN fields[1] = pg_catalog.convert_to(p_state,'UTF8')
       AND fields[2] IS NOT DISTINCT FROM modkit_events._optional_bytes(p_codec)
       AND fields[3] IS NOT DISTINCT FROM modkit_events._optional_bytes(p_key_version)
       AND fields[4] IS NOT DISTINCT FROM modkit_events._optional_bytes(expiry_bytes)
       AND fields[5] = pg_catalog.convert_to(p_cleanup,'UTF8')
       AND fields[6] IS NOT DISTINCT FROM modkit_events._optional_bytes(p_sidecar)
       AND fields[7] IS NOT DISTINCT FROM modkit_events._optional_bytes(p_reference)
       AND fields[9] = p_recovery AND fields[10] = p_projection;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._protected_valid(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events._intent_valid(
    p_kind pg_catalog.text, p_subscription pg_catalog.bytea,
    p_namespace pg_catalog.bytea, p_command pg_catalog.bytea,
    p_scope pg_catalog.bytea, p_key pg_catalog.bytea,
    p_canonical_version pg_catalog.int4, p_schema_version pg_catalog.bytea,
    p_application pg_catalog.bytea, p_tenant pg_catalog.bytea, p_owner pg_catalog.bytea,
    p_intent pg_catalog.bytea, p_semantic pg_catalog.bytea, p_replay pg_catalog.bytea,
    p_protected pg_catalog.bytea, p_replay_policy pg_catalog.text, p_max_attempts pg_catalog.int4,
    p_deadline pg_catalog.timestamptz, p_original_available_at pg_catalog.timestamptz)
RETURNS pg_catalog.bool LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE item pg_catalog.bytea; expected pg_catalog.bytea; semantic pg_catalog.bytea;
    available_bytes pg_catalog.bytea; deadline_bytes pg_catalog.bytea; envelope_fields pg_catalog.bytea[];
BEGIN
    IF p_kind IS NULL OR p_kind NOT IN ('job','inbox') OR p_canonical_version IS DISTINCT FROM 1
       OR p_replay_policy IS NULL OR p_replay_policy NOT IN ('disabled','application_safe')
       OR p_max_attempts IS NULL OR p_max_attempts < 1 OR p_max_attempts > 1000
       OR p_intent IS NULL OR p_semantic IS NULL OR p_replay IS NULL OR p_protected IS NULL
       OR p_schema_version IS NULL OR p_namespace IS NULL OR p_command IS NULL OR p_scope IS NULL OR p_application IS NULL
       OR (p_kind = 'job') <> (p_subscription IS NULL) THEN RETURN FALSE; END IF;
    FOREACH item IN ARRAY ARRAY[p_intent,p_semantic,p_replay,p_protected]::pg_catalog.bytea[] LOOP
        IF pg_catalog.octet_length(item) > 1048576 THEN RETURN FALSE; END IF;
    END LOOP;
    FOREACH item IN ARRAY ARRAY[p_namespace,p_command,p_subscription,p_key]::pg_catalog.bytea[] LOOP
        IF item IS NOT NULL AND NOT modkit_events._utf8_valid(item,256,TRUE) THEN RETURN FALSE; END IF;
    END LOOP;
    IF NOT modkit_events._decimal_valid(p_schema_version,FALSE)
       OR NOT modkit_events._scope_valid(p_scope,p_application,p_tenant,p_owner) THEN RETURN FALSE; END IF;
    available_bytes := modkit_events._instant_bytes(p_original_available_at);
    IF available_bytes IS NULL THEN RETURN FALSE; END IF;
    IF p_deadline IS NOT NULL THEN
        deadline_bytes := modkit_events._instant_bytes(p_deadline);
        IF deadline_bytes IS NULL THEN RETURN FALSE; END IF;
    END IF;
    IF p_kind = 'job' THEN
        semantic := modkit_events._json_to_j(p_replay);
        IF semantic IS NULL THEN RETURN FALSE; END IF;
        IF pg_catalog.get_byte(semantic,0) <> 111 THEN RETURN FALSE; END IF;
    ELSE
        semantic := modkit_events._event_replay_frame(p_replay);
        IF semantic IS NULL THEN RETURN FALSE; END IF;
        envelope_fields := modkit_events._record_fields(semantic,pg_catalog.convert_to('event-envelope','UTF8'),5);
        IF envelope_fields[2] IS DISTINCT FROM p_command OR envelope_fields[3] IS DISTINCT FROM p_schema_version THEN RETURN FALSE; END IF;
    END IF;
    IF semantic IS DISTINCT FROM p_semantic THEN RETURN FALSE; END IF;
    expected := modkit_events._make_record(pg_catalog.convert_to('work-intent','UTF8'),ARRAY[
        pg_catalog.convert_to(p_kind,'UTF8'),modkit_events._optional_bytes(p_subscription),p_namespace,p_command,
        p_schema_version,pg_catalog.decode('31','hex'),p_scope,modkit_events._optional_bytes(p_key),p_semantic,p_protected,
        pg_catalog.convert_to(p_replay_policy,'UTF8'),pg_catalog.convert_to(p_max_attempts::pg_catalog.text,'UTF8'),
        modkit_events._optional_bytes(deadline_bytes),available_bytes]::pg_catalog.bytea[]);
    RETURN expected IS NOT NULL AND expected = p_intent;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._intent_valid(pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.timestamptz,pg_catalog.timestamptz) FROM PUBLIC;

CREATE TABLE modkit_events.schema_versions (
    component pg_catalog.text PRIMARY KEY CHECK (component IN ('events','workers')),
    version pg_catalog.int4 NOT NULL CHECK (version = 1),
    migration_digest pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(migration_digest) = 32),
    catalog_contract_id pg_catalog.text NOT NULL CHECK (catalog_contract_id = 'modkit-pg-ab-2'),
    scope_format_id pg_catalog.text NOT NULL CHECK (scope_format_id = 'MKSC-1'),
    intent_format_id pg_catalog.text NOT NULL CHECK (intent_format_id = 'MKPF-1'),
    applied_at pg_catalog.timestamptz NOT NULL
);
REVOKE ALL ON TABLE modkit_events.schema_versions FROM PUBLIC;

CREATE TABLE modkit_events.subscriptions (
    subscription_id pg_catalog.bytea PRIMARY KEY CHECK (modkit_events._utf8_valid(subscription_id,256,TRUE)),
    manifest pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(manifest) <= 1048576),
    consumer_group pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(consumer_group,256,TRUE)),
    capacity pg_catalog.int4 NOT NULL CHECK (capacity > 0),
    nonterminal_count pg_catalog.int8 NOT NULL CHECK (nonterminal_count >= 0 AND nonterminal_count <= capacity),
    created_at pg_catalog.timestamptz NOT NULL
);
REVOKE ALL ON TABLE modkit_events.subscriptions FROM PUBLIC;

CREATE TABLE modkit_events.work (
    work_id pg_catalog.uuid PRIMARY KEY,
    kind pg_catalog.text NOT NULL CHECK (kind IN ('job','inbox')),
    subscription_id pg_catalog.bytea REFERENCES modkit_events.subscriptions(subscription_id),
    namespace pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(namespace,256,TRUE)),
    command_type pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(command_type,256,TRUE)),
    schema_version_decimal pg_catalog.bytea NOT NULL CHECK (modkit_events._decimal_valid(schema_version_decimal,FALSE)),
    runnable_version pg_catalog.int4 CHECK (runnable_version > 0),
    canonical_version pg_catalog.int4 NOT NULL CHECK (canonical_version = 1),
    scope_evidence pg_catalog.bytea NOT NULL,
    scope_application pg_catalog.bytea NOT NULL,
    scope_tenant pg_catalog.bytea,
    scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea CHECK (idempotency_key IS NULL OR modkit_events._utf8_valid(idempotency_key,256,TRUE)),
    intent_evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(intent_evidence) BETWEEN 1 AND 1048576),
    semantic_input pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(semantic_input) BETWEEN 1 AND 1048576),
    replay_input pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(replay_input) BETWEEN 1 AND 1048576),
    protected_binding pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(protected_binding) <= 1048576),
    replay_policy pg_catalog.text NOT NULL CHECK (replay_policy IN ('disabled','application_safe')),
    max_attempts pg_catalog.int4 NOT NULL CHECK (max_attempts BETWEEN 1 AND 1000),
    deadline pg_catalog.timestamptz,
    original_available_at pg_catalog.timestamptz NOT NULL,
    state pg_catalog.text NOT NULL CHECK (state IN ('queued','claimed','running','retry_waiting','succeeded','failed','expired','cancelled','blocked_schema','held')),
    cancellation_requested pg_catalog.bool NOT NULL,
    token pg_catalog.uuid,
    ownership_revision pg_catalog.int8 NOT NULL CHECK (ownership_revision >= 0),
    lease_until pg_catalog.timestamptz,
    available_at pg_catalog.timestamptz NOT NULL,
    cycle pg_catalog.int4 NOT NULL CHECK (cycle >= 1),
    attempt_count pg_catalog.int4 NOT NULL CHECK (attempt_count >= 0 AND attempt_count <= max_attempts),
    dispatch_id pg_catalog.uuid,
    result pg_catalog.bytea CHECK (result IS NULL OR pg_catalog.octet_length(result) <= 1048576),
    created_at pg_catalog.timestamptz NOT NULL,
    updated_at pg_catalog.timestamptz NOT NULL,
    success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid,
    final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea,
    resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid,
    CHECK ((kind = 'job') = (subscription_id IS NULL)),
    CHECK (modkit_events._scope_valid(scope_evidence,scope_application,scope_tenant,scope_owner)),
    CHECK (runnable_version IS NULL OR schema_version_decimal = pg_catalog.convert_to(runnable_version::pg_catalog.text,'UTF8')),
    CHECK ((state IN ('claimed','running') AND token IS NOT NULL AND lease_until IS NOT NULL)
        OR (state NOT IN ('claimed','running') AND token IS NULL AND lease_until IS NULL)),
    CHECK (state NOT IN ('queued','claimed','retry_waiting','blocked_schema') OR dispatch_id IS NULL),
    CHECK (state NOT IN ('running','held','succeeded') OR (dispatch_id IS NOT NULL AND attempt_count > 0)),
    CHECK ((
       (state = 'succeeded' AND result IS NOT NULL AND dispatch_id IS NOT NULL AND
          ((success_origin = 'guarded' AND completion_guard_id IS NOT NULL AND final_fence_at IS NOT NULL
            AND completion_result_digest IS NOT NULL AND pg_catalog.octet_length(completion_result_digest) = 32
            AND resolution_operation_id IS NULL AND terminal_resolution_operation_id IS NULL)
           OR (success_origin = 'reconciled' AND completion_guard_id IS NULL AND final_fence_at IS NULL
            AND completion_result_digest IS NULL AND resolution_operation_id IS NOT NULL
            AND terminal_resolution_operation_id IS NOT NULL AND resolution_operation_id = terminal_resolution_operation_id)))
       OR (state <> 'succeeded' AND success_origin IS NULL AND completion_guard_id IS NULL
           AND final_fence_at IS NULL AND completion_result_digest IS NULL AND resolution_operation_id IS NULL
           AND (state IN ('failed','cancelled') OR terminal_resolution_operation_id IS NULL))
    ) IS TRUE)
);
REVOKE ALL ON TABLE modkit_events.work FROM PUBLIC;
CREATE UNIQUE INDEX work_key_identity ON modkit_events.work
    (kind, pg_catalog.sha256(subscription_id), namespace, command_type, pg_catalog.sha256(scope_evidence), pg_catalog.sha256(idempotency_key))
    NULLS NOT DISTINCT WHERE idempotency_key IS NOT NULL;
CREATE INDEX work_discovery_scan ON modkit_events.work (namespace,kind,work_id);
CREATE INDEX work_ready_scan ON modkit_events.work (namespace,kind,work_id)
    WHERE state IN ('queued','retry_waiting');
CREATE INDEX work_recovery_scan ON modkit_events.work (namespace,kind,work_id)
    WHERE state IN ('claimed','running','queued','retry_waiting','blocked_schema');

CREATE TABLE modkit_events.finalization_guards (
    guard_id pg_catalog.uuid PRIMARY KEY,
    work_id pg_catalog.uuid NOT NULL REFERENCES modkit_events.work(work_id),
    root_xid pg_catalog.xid8 NOT NULL,
    token pg_catalog.uuid NOT NULL,
    ownership_revision pg_catalog.int8 NOT NULL CHECK (ownership_revision > 0),
    cycle pg_catalog.int4 NOT NULL CHECK (cycle >= 1),
    expected_attempt pg_catalog.int4 NOT NULL CHECK (expected_attempt BETWEEN 1 AND 1000),
    satisfied pg_catalog.bool NOT NULL,
    final_fence_at pg_catalog.timestamptz,
    terminal_state pg_catalog.text,
    result_digest pg_catalog.bytea,
    UNIQUE (work_id,root_xid),
    CHECK ((NOT satisfied AND final_fence_at IS NULL AND terminal_state IS NULL AND result_digest IS NULL)
        OR (satisfied AND final_fence_at IS NOT NULL AND terminal_state IS NOT NULL AND terminal_state = 'succeeded'
            AND result_digest IS NOT NULL AND pg_catalog.octet_length(result_digest) = 32))
);
REVOKE ALL ON TABLE modkit_events.finalization_guards FROM PUBLIC;

CREATE FUNCTION modkit_events._guard_immutable()
RETURNS pg_catalog.trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='guard mutation rejected';
    END IF;
    IF OLD.satisfied OR NEW.guard_id IS DISTINCT FROM OLD.guard_id OR NEW.work_id IS DISTINCT FROM OLD.work_id
       OR NEW.root_xid IS DISTINCT FROM OLD.root_xid OR NEW.token IS DISTINCT FROM OLD.token
       OR NEW.ownership_revision IS DISTINCT FROM OLD.ownership_revision OR NEW.cycle IS DISTINCT FROM OLD.cycle
       OR NEW.expected_attempt IS DISTINCT FROM OLD.expected_attempt OR NOT NEW.satisfied THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='guard mutation rejected';
    END IF;
    RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._guard_immutable() FROM PUBLIC;
CREATE TRIGGER guard_immutable BEFORE UPDATE OR DELETE ON modkit_events.finalization_guards
    FOR EACH ROW EXECUTE FUNCTION modkit_events._guard_immutable();

CREATE FUNCTION modkit_events._guard_deferred_check()
RETURNS pg_catalog.trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE persisted_satisfied pg_catalog.bool;
BEGIN
    SELECT g.satisfied INTO persisted_satisfied FROM modkit_events.finalization_guards AS g WHERE g.guard_id = NEW.guard_id;
    IF persisted_satisfied IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ001',MESSAGE='unsatisfied finalization guard';
    END IF;
    RETURN NULL;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._guard_deferred_check() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER guard_requires_certificate AFTER INSERT OR UPDATE ON modkit_events.finalization_guards
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION modkit_events._guard_deferred_check();

CREATE TABLE modkit_events.inbox (
    work_id pg_catalog.uuid PRIMARY KEY REFERENCES modkit_events.work(work_id),
    subscription_id pg_catalog.bytea NOT NULL REFERENCES modkit_events.subscriptions(subscription_id),
    event_id pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(event_id,256,TRUE)),
    event_digest pg_catalog.bytea GENERATED ALWAYS AS (pg_catalog.sha256(event_id)) STORED,
    envelope_evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(envelope_evidence) BETWEEN 1 AND 1048576),
    replay_input pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(replay_input) BETWEEN 1 AND 1048576),
    UNIQUE(subscription_id,event_digest)
);
REVOKE ALL ON TABLE modkit_events.inbox FROM PUBLIC;

CREATE TABLE modkit_events.attempts (
    work_id pg_catalog.uuid NOT NULL REFERENCES modkit_events.work(work_id),
    cycle pg_catalog.int4 NOT NULL CHECK (cycle >= 1),
    attempt pg_catalog.int4 NOT NULL CHECK (attempt BETWEEN 1 AND 1000),
    dispatch_id pg_catalog.uuid NOT NULL UNIQUE,
    effect_id pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(effect_id,256,TRUE)),
    request_evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(request_evidence) <= 1048576),
    provider_key_reference pg_catalog.bytea CHECK (provider_key_reference IS NULL OR modkit_events._utf8_valid(provider_key_reference,256,TRUE)),
    dispatch_root_xid pg_catalog.xid8 NOT NULL,
    outcome pg_catalog.text NOT NULL,
    evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(evidence) <= 1048576),
    recorded_at pg_catalog.timestamptz NOT NULL,
    PRIMARY KEY (work_id,cycle,attempt)
);
REVOKE ALL ON TABLE modkit_events.attempts FROM PUBLIC;

CREATE TABLE modkit_events.work_history (
    history_id pg_catalog.int8 GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_id pg_catalog.uuid NOT NULL REFERENCES modkit_events.work(work_id),
    cycle pg_catalog.int4 NOT NULL,
    attempt pg_catalog.int4 NOT NULL,
    transition pg_catalog.text NOT NULL,
    reason pg_catalog.text NOT NULL,
    token pg_catalog.uuid,
    ownership_revision pg_catalog.int8 NOT NULL,
    evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(evidence) <= 1048576),
    recorded_at pg_catalog.timestamptz NOT NULL
);
REVOKE ALL ON TABLE modkit_events.work_history FROM PUBLIC;
REVOKE ALL ON SEQUENCE modkit_events.work_history_history_id_seq FROM PUBLIC;
CREATE INDEX work_history_page ON modkit_events.work_history(work_id,history_id);

CREATE TABLE modkit_events.delivery_history (
    history_id pg_catalog.int8 GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_id pg_catalog.uuid NOT NULL REFERENCES modkit_events.inbox(work_id),
    broker_reference pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(broker_reference) <= 1048576),
    transport_observation pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(transport_observation) <= 1048576),
    recorded_at pg_catalog.timestamptz NOT NULL
);
REVOKE ALL ON TABLE modkit_events.delivery_history FROM PUBLIC;
REVOKE ALL ON SEQUENCE modkit_events.delivery_history_history_id_seq FROM PUBLIC;
CREATE INDEX delivery_history_page ON modkit_events.delivery_history(work_id,history_id);

CREATE TABLE modkit_events.outbox (
    event_id pg_catalog.bytea NOT NULL CHECK (modkit_events._utf8_valid(event_id,256,TRUE)),
    event_digest pg_catalog.bytea GENERATED ALWAYS AS (pg_catalog.sha256(event_id)) STORED PRIMARY KEY,
    canonical_version pg_catalog.int4 NOT NULL CHECK (canonical_version = 1),
    envelope_evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(envelope_evidence) BETWEEN 1 AND 1048576),
    replay_input pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(replay_input) BETWEEN 1 AND 1048576),
    state pg_catalog.text NOT NULL CHECK (state IN ('pending','claimed','publishing','published','rejected','held')),
    token pg_catalog.uuid,
    ownership_revision pg_catalog.int8 NOT NULL CHECK (ownership_revision >= 0),
    lease_until pg_catalog.timestamptz,
    intent_id pg_catalog.uuid UNIQUE,
    receipt pg_catalog.bytea CHECK (receipt IS NULL OR pg_catalog.octet_length(receipt) <= 4096),
    outcome_evidence pg_catalog.bytea CHECK (outcome_evidence IS NULL OR pg_catalog.octet_length(outcome_evidence) <= 1048576),
    created_at pg_catalog.timestamptz NOT NULL,
    updated_at pg_catalog.timestamptz NOT NULL,
    CHECK ((state IN ('claimed','publishing') AND token IS NOT NULL AND lease_until IS NOT NULL)
        OR (state NOT IN ('claimed','publishing') AND token IS NULL AND lease_until IS NULL)),
    CHECK ((state IN ('pending','claimed') AND intent_id IS NULL)
        OR (state IN ('publishing','published','rejected','held') AND intent_id IS NOT NULL))
);
REVOKE ALL ON TABLE modkit_events.outbox FROM PUBLIC;
CREATE INDEX outbox_scan ON modkit_events.outbox(event_digest) WHERE state IN ('pending','claimed','publishing');

CREATE TABLE modkit_events.publication_history (
    history_id pg_catalog.int8 GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id pg_catalog.bytea NOT NULL,
    event_digest pg_catalog.bytea GENERATED ALWAYS AS (pg_catalog.sha256(event_id)) STORED REFERENCES modkit_events.outbox(event_digest),
    intent_id pg_catalog.uuid,
    operation_id pg_catalog.uuid,
    status pg_catalog.text NOT NULL,
    receipt pg_catalog.bytea CHECK (receipt IS NULL OR pg_catalog.octet_length(receipt) <= 4096),
    evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(evidence) <= 1048576),
    binding pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(binding) <= 1048576),
    recorded_at pg_catalog.timestamptz NOT NULL
);
REVOKE ALL ON TABLE modkit_events.publication_history FROM PUBLIC;
REVOKE ALL ON SEQUENCE modkit_events.publication_history_history_id_seq FROM PUBLIC;
CREATE INDEX publication_history_page ON modkit_events.publication_history(event_digest,history_id);

-- Segment3: private relational record invariants only. Still NOT_READY.
ALTER TABLE modkit_events.attempts
    ADD CONSTRAINT attempt_current_cycle CHECK (cycle = 1),
    ADD CONSTRAINT attempt_outcome_domain CHECK (outcome IN
      ('dispatched','succeeded','failed','cancelled','uncertain','cancelled_unresolved','safe_retry')),
    ADD CONSTRAINT attempt_generated_evidence CHECK
      (outcome NOT IN ('dispatched','cancelled_unresolved') OR evidence = ''::pg_catalog.bytea);

ALTER TABLE modkit_events.work_history
    ADD CONSTRAINT history_current_cycle CHECK (cycle = 1),
    ADD CONSTRAINT history_code_and_attempt CHECK ((
      (transition IN ('intake_runnable','intake_blocked') AND attempt = 0)
      OR (transition IN ('claim','defer','recover_claim') AND attempt BETWEEN 0 AND 999)
      OR (transition IN ('failure_retry','reconcile_safe_retry') AND attempt BETWEEN 1 AND 999)
      OR (transition IN ('renew','cancel_predispatch','recover_expired_predispatch') AND attempt BETWEEN 0 AND 1000)
      OR (transition IN ('dispatch','complete','failure_terminal','failure_cancelled','cancel_running','cancel_held',
           'recover_exhausted_predispatch','recover_dispatched','reconcile_success','reconcile_rejection','reconcile_cancelled','hold_uncertain') AND attempt BETWEEN 1 AND 1000)
    ) IS TRUE),
    ADD CONSTRAINT history_ownership_shape CHECK ((
      (transition IN ('intake_runnable','intake_blocked') AND ownership_revision = 0 AND token IS NULL)
      OR (transition IN ('claim','renew','dispatch') AND ownership_revision > 0 AND token IS NOT NULL)
      OR (transition NOT IN ('intake_runnable','intake_blocked','claim','renew','dispatch') AND ownership_revision > 0 AND token IS NULL)
    ) IS TRUE),
    ADD CONSTRAINT history_reason_shape CHECK ((
      reason COLLATE pg_catalog."C" OPERATOR(pg_catalog.~) '^[a-z][a-z0-9_]{0,255}$'
      AND (transition IN ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain')
        OR (transition = 'recover_exhausted_predispatch' AND reason = 'attempts_exhausted')
        OR (transition NOT IN ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain','recover_exhausted_predispatch') AND reason = transition))
    ) IS TRUE),
    ADD CONSTRAINT history_evidence_origin CHECK
      (transition IN ('failure_terminal','failure_cancelled','failure_retry','reconcile_success','reconcile_rejection','reconcile_cancelled','reconcile_safe_retry','hold_uncertain') OR evidence = ''::pg_catalog.bytea);

ALTER TABLE modkit_events.publication_history
    ADD CONSTRAINT publication_code_shape CHECK ((
      (status IN ('enqueue','claim_publication','recover_publication_preintent') AND intent_id IS NULL AND operation_id IS NULL AND receipt IS NULL)
      OR (status = 'renew_publication' AND operation_id IS NULL AND receipt IS NULL)
      OR (status IN ('publication_intent','recover_publication_intent') AND intent_id IS NOT NULL AND operation_id IS NULL AND receipt IS NULL)
      OR (status IN ('publication_confirmed','publication_rejected','publication_uncertain') AND intent_id IS NOT NULL AND operation_id IS NULL)
      OR (status IN ('repair_published','repair_rejected') AND intent_id IS NOT NULL AND operation_id IS NOT NULL)
    ) IS TRUE),
    ADD CONSTRAINT publication_binding_origin CHECK
      (status IN ('repair_published','repair_rejected') OR binding = ''::pg_catalog.bytea),
    ADD CONSTRAINT publication_evidence_origin CHECK
      (status IN ('publication_confirmed','publication_rejected','publication_uncertain','repair_published','repair_rejected') OR evidence = ''::pg_catalog.bytea);

CREATE FUNCTION modkit_events._reject_record_mutation()
RETURNS pg_catalog.trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='immutable record mutation rejected';
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._reject_record_mutation() FROM PUBLIC;
CREATE TRIGGER work_history_immutable BEFORE UPDATE OR DELETE ON modkit_events.work_history
    FOR EACH ROW EXECUTE FUNCTION modkit_events._reject_record_mutation();
CREATE TRIGGER delivery_history_immutable BEFORE UPDATE OR DELETE ON modkit_events.delivery_history
    FOR EACH ROW EXECUTE FUNCTION modkit_events._reject_record_mutation();
CREATE TRIGGER publication_history_immutable BEFORE UPDATE OR DELETE ON modkit_events.publication_history
    FOR EACH ROW EXECUTE FUNCTION modkit_events._reject_record_mutation();

CREATE FUNCTION modkit_events._attempt_record_check()
RETURNS pg_catalog.trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='immutable attempt deletion rejected';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.outcome IS DISTINCT FROM 'dispatched' OR NEW.evidence IS DISTINCT FROM ''::pg_catalog.bytea THEN
            RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid initial attempt';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.work_id IS DISTINCT FROM OLD.work_id OR NEW.cycle IS DISTINCT FROM OLD.cycle
       OR NEW.attempt IS DISTINCT FROM OLD.attempt OR NEW.dispatch_id IS DISTINCT FROM OLD.dispatch_id
       OR NEW.effect_id IS DISTINCT FROM OLD.effect_id OR NEW.request_evidence IS DISTINCT FROM OLD.request_evidence
       OR NEW.provider_key_reference IS DISTINCT FROM OLD.provider_key_reference
       OR NEW.dispatch_root_xid IS DISTINCT FROM OLD.dispatch_root_xid OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='immutable dispatch identity changed';
    END IF;
    IF ((OLD.outcome = 'dispatched' AND NEW.outcome IN ('succeeded','failed','cancelled','uncertain','cancelled_unresolved'))
       OR (OLD.outcome IN ('uncertain','cancelled_unresolved') AND NEW.outcome IN ('succeeded','failed','cancelled','safe_retry'))) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid attempt outcome transition';
    END IF;
    IF OLD.outcome = 'dispatched' AND NEW.outcome = 'succeeded' AND NEW.evidence IS DISTINCT FROM ''::pg_catalog.bytea THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid generated attempt evidence';
    END IF;
    -- Local edge only: producer authority/work locks/root/fence checked by future
    -- private/public operations, never inferred from this row's outcome alone.
    RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._attempt_record_check() FROM PUBLIC;
CREATE TRIGGER attempt_record_check BEFORE INSERT OR UPDATE OR DELETE ON modkit_events.attempts
    FOR EACH ROW EXECUTE FUNCTION modkit_events._attempt_record_check();

-- Exact stored request/observation union; no standalone runtime read API.
-- Immutable request fields are compared individually by future E27/E31/E32.
CREATE TABLE modkit_events.mutation_operations (
    operation_id pg_catalog.uuid PRIMARY KEY,
    operation_kind pg_catalog.text NOT NULL,
    work_id pg_catalog.uuid REFERENCES modkit_events.work(work_id),
    event_id pg_catalog.bytea CHECK (event_id IS NULL OR modkit_events._utf8_valid(event_id,256,TRUE)),
    event_digest pg_catalog.bytea GENERATED ALWAYS AS (pg_catalog.sha256(event_id)) STORED REFERENCES modkit_events.outbox(event_digest),
    expected_revision pg_catalog.int8 NOT NULL CHECK (expected_revision >= 0),
    token pg_catalog.uuid,
    cycle pg_catalog.int4,
    attempt pg_catalog.int4,
    dispatch_id pg_catalog.uuid,
    failed_business_root pg_catalog.xid8,
    requested_outcome pg_catalog.text,
    retry_at pg_catalog.timestamptz CHECK (retry_at IS NULL OR modkit_events._instant_bytes(retry_at) IS NOT NULL),
    requested_result pg_catalog.bytea CHECK (requested_result IS NULL OR pg_catalog.octet_length(requested_result) <= 1048576),
    result_digest pg_catalog.bytea,
    requested_reason pg_catalog.text CHECK (requested_reason IS NULL OR requested_reason COLLATE pg_catalog."C" OPERATOR(pg_catalog.~) '^[a-z][a-z0-9_]{0,255}$'),
    requested_receipt pg_catalog.bytea CHECK (requested_receipt IS NULL OR pg_catalog.octet_length(requested_receipt) <= 4096),
    evidence pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(evidence) <= 1048576),
    binding pg_catalog.bytea NOT NULL CHECK (pg_catalog.octet_length(binding) <= 1048576),
    resolution_root_xid pg_catalog.xid8,
    resulting_revision pg_catalog.int8,
    recorded_at pg_catalog.timestamptz NOT NULL CHECK (modkit_events._instant_bytes(recorded_at) IS NOT NULL),
    CONSTRAINT operation_typed_union CHECK ((
      (operation_kind = 'repair_publication' AND event_id IS NOT NULL AND work_id IS NULL
       AND token IS NULL AND cycle IS NULL AND attempt IS NULL AND dispatch_id IS NULL AND failed_business_root IS NULL
       AND requested_outcome IN ('published','rejected') AND retry_at IS NULL
       AND requested_result IS NULL AND result_digest IS NULL AND requested_reason IS NULL AND resolution_root_xid IS NULL
       AND resulting_revision IS NOT NULL AND resulting_revision::pg_catalog.numeric = expected_revision::pg_catalog.numeric + 1)
      OR
      (operation_kind = 'reconcile_work' AND work_id IS NOT NULL AND event_id IS NULL AND token IS NULL
       AND cycle = 1 AND attempt BETWEEN 1 AND 1000 AND dispatch_id IS NOT NULL
       AND failed_business_root IS NULL AND requested_receipt IS NULL AND requested_reason IS NULL
       AND resolution_root_xid IS NOT NULL AND resolution_root_xid > '0'::pg_catalog.xid8 AND resulting_revision IS NULL
       AND ((requested_outcome = 'confirmed_success' AND retry_at IS NULL AND requested_result IS NOT NULL
             AND result_digest IS NOT NULL AND result_digest = pg_catalog.sha256(requested_result))
         OR (requested_outcome IN ('confirmed_rejection','confirmed_cancelled') AND retry_at IS NULL AND requested_result IS NULL AND result_digest IS NULL)
         OR (requested_outcome = 'safe_retry' AND retry_at IS NOT NULL AND requested_result IS NULL AND result_digest IS NULL AND attempt < 1000)))
      OR
      (operation_kind = 'hold_uncertain' AND work_id IS NOT NULL AND event_id IS NULL AND token IS NOT NULL
       AND expected_revision > 0 AND cycle = 1 AND attempt BETWEEN 1 AND 1000 AND dispatch_id IS NOT NULL
       AND failed_business_root IS NOT NULL AND failed_business_root > '0'::pg_catalog.xid8
       AND requested_reason IS NOT NULL AND requested_outcome IS NULL AND retry_at IS NULL
       AND requested_result IS NULL AND result_digest IS NULL AND requested_receipt IS NULL AND resolution_root_xid IS NULL
       AND resulting_revision IS NOT NULL AND resulting_revision::pg_catalog.numeric = expected_revision::pg_catalog.numeric + 1)
    ) IS TRUE)
);
REVOKE ALL ON TABLE modkit_events.mutation_operations FROM PUBLIC;
CREATE TRIGGER mutation_operations_immutable BEFORE UPDATE OR DELETE ON modkit_events.mutation_operations
    FOR EACH ROW EXECUTE FUNCTION modkit_events._reject_record_mutation();

ALTER TABLE modkit_events.attempts
    ADD CONSTRAINT attempt_root_positive CHECK (dispatch_root_xid > '0'::pg_catalog.xid8),
    ADD CONSTRAINT attempt_time_supported CHECK (modkit_events._instant_bytes(recorded_at) IS NOT NULL);
ALTER TABLE modkit_events.work_history
    ADD CONSTRAINT work_history_id_positive CHECK (history_id > 0),
    ADD CONSTRAINT work_history_time_supported CHECK (modkit_events._instant_bytes(recorded_at) IS NOT NULL);
ALTER TABLE modkit_events.delivery_history
    ADD CONSTRAINT delivery_history_id_positive CHECK (history_id > 0),
    ADD CONSTRAINT delivery_history_time_supported CHECK (modkit_events._instant_bytes(recorded_at) IS NOT NULL);
ALTER TABLE modkit_events.publication_history
    ADD CONSTRAINT publication_history_id_positive CHECK (history_id > 0),
    ADD CONSTRAINT publication_history_event_valid CHECK (modkit_events._utf8_valid(event_id,256,TRUE)),
    ADD CONSTRAINT publication_history_time_supported CHECK (modkit_events._instant_bytes(recorded_at) IS NOT NULL);

-- Segment4: bounded public root/guard observations only. Still NOT_READY.
-- E14 may assign the caller's actual top-level xid; it owns no transaction.
CREATE FUNCTION modkit_events.e14()
RETURNS TABLE(root_xid pg_catalog.xid8)
LANGUAGE plpgsql VOLATILE SECURITY INVOKER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    RETURN QUERY SELECT pg_catalog.pg_current_xact_id();
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e14() FROM PUBLIC;

-- E09 is persisted unsatisfied-guard observation, not a live work fence.
-- No supplied root, hidden xid allocation, row lock or mutation is permitted.
CREATE FUNCTION modkit_events.e09(
    p_work_id pg_catalog.uuid,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4
)
RETURNS TABLE(
    guard_id pg_catalog.uuid,
    work_id pg_catalog.uuid,
    root_xid pg_catalog.xid8,
    token pg_catalog.uuid,
    ownership_revision pg_catalog.int8,
    cycle pg_catalog.int4,
    expected_attempt pg_catalog.int4,
    satisfied pg_catalog.bool,
    final_fence_at pg_catalog.timestamptz,
    terminal_state pg_catalog.text,
    result_digest pg_catalog.bytea
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE actual_root pg_catalog.xid8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_token IS NULL OR p_ownership_revision IS NULL
       OR p_cycle IS NULL OR p_expected_attempt IS NULL
       OR p_ownership_revision <= 0 OR p_cycle <> 1
       OR p_expected_attempt < 0 OR p_expected_attempt > 1000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid guard fence';
    END IF;
    actual_root := pg_catalog.pg_current_xact_id_if_assigned();
    IF actual_root IS NULL THEN RETURN; END IF;
    RETURN QUERY
      SELECT g.guard_id,g.work_id,g.root_xid,g.token,g.ownership_revision,
        g.cycle,g.expected_attempt,g.satisfied,g.final_fence_at,g.terminal_state,g.result_digest
      FROM modkit_events.finalization_guards AS g
      WHERE g.work_id = p_work_id AND g.root_xid = actual_root
        AND g.token = p_token AND g.ownership_revision = p_ownership_revision
        AND g.cycle = p_cycle AND g.expected_attempt = p_expected_attempt
        AND NOT g.satisfied;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e09(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

-- Segment5: bounded E08 guard production only. Still NOT_READY.
-- Arming retains the immediate FK KEY SHARE, not an ownership/final fence.
CREATE FUNCTION modkit_events.e08(
    p_work_id pg_catalog.uuid,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4
)
RETURNS TABLE(
    guard_id pg_catalog.uuid,
    work_id pg_catalog.uuid,
    root_xid pg_catalog.xid8,
    token pg_catalog.uuid,
    ownership_revision pg_catalog.int8,
    cycle pg_catalog.int4,
    expected_attempt pg_catalog.int4,
    satisfied pg_catalog.bool,
    final_fence_at pg_catalog.timestamptz,
    terminal_state pg_catalog.text,
    result_digest pg_catalog.bytea
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    actual_root pg_catalog.xid8;
    preliminary pg_catalog.record;
    current_row pg_catalog.record;
    inserted_guard pg_catalog.record;
    current_exists pg_catalog.bool;
    observed_at pg_catalog.timestamptz;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_token IS NULL OR p_ownership_revision IS NULL
       OR p_cycle IS NULL OR p_expected_attempt IS NULL
       OR p_ownership_revision <= 0 OR p_cycle <> 1
       OR p_expected_attempt < 0 OR p_expected_attempt > 1000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid guard fence';
    END IF;
    actual_root := pg_catalog.pg_current_xact_id();
    IF EXISTS(SELECT 1 FROM modkit_events.finalization_guards AS g
              WHERE g.work_id = p_work_id AND g.root_xid = actual_root) THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='guard already exists in current root';
    END IF;

    -- Preliminary classification prevents legal Fence attempt0 from reaching
    -- the guard's positive-attempt CHECK. It does not authorize successful arm.
    SELECT w.token,w.ownership_revision,w.cycle,w.attempt_count,w.state
      INTO preliminary FROM modkit_events.work AS w WHERE w.work_id = p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF preliminary.token IS DISTINCT FROM p_token
       OR preliminary.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR preliminary.cycle IS DISTINCT FROM p_cycle
       OR preliminary.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF preliminary.state IS DISTINCT FROM 'running' THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='work is not running';
    END IF;
    IF preliminary.attempt_count IS NULL OR preliminary.attempt_count < 1 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='inconsistent running work';
    END IF;

    -- Immediate FK may wait. Caller-selected IMMEDIATE guard mode fails here;
    -- do not alter constraint mode or catch a native/constraint error.
    INSERT INTO modkit_events.finalization_guards AS g
      (guard_id,work_id,root_xid,token,ownership_revision,cycle,expected_attempt,
       satisfied,final_fence_at,terminal_state,result_digest)
      VALUES(pg_catalog.gen_random_uuid(),p_work_id,actual_root,p_token,
        p_ownership_revision,p_cycle,p_expected_attempt,FALSE,NULL,NULL,NULL)
      RETURNING g.guard_id,g.work_id,g.root_xid,g.token,g.ownership_revision,
        g.cycle,g.expected_attempt,g.satisfied,g.final_fence_at,g.terminal_state,g.result_digest
      INTO inserted_guard;

    -- Separate post-wait statement snapshot. Preserve missing attempt with
    -- LEFT JOIN; no locking ownership read and no reuse of preliminary data.
    SELECT w.work_id,w.token,w.ownership_revision,w.cycle,w.attempt_count,w.state,
        w.max_attempts,w.runnable_version,w.lease_until,w.deadline,w.cancellation_requested,
        w.dispatch_id,w.result,w.success_origin,w.completion_guard_id,w.final_fence_at,
        w.completion_result_digest,w.resolution_operation_id,w.terminal_resolution_operation_id,
        a.work_id AS attempt_work_id,a.cycle AS attempt_cycle,a.attempt AS attempt_ordinal,
        a.dispatch_id AS attempt_dispatch_id,a.outcome AS attempt_outcome,
        a.evidence AS attempt_evidence,a.dispatch_root_xid,a.recorded_at AS attempt_recorded_at
      INTO current_row
      FROM modkit_events.work AS w
      LEFT JOIN modkit_events.attempts AS a
        ON a.work_id = w.work_id AND a.cycle = w.cycle AND a.attempt = w.attempt_count
      WHERE w.work_id = p_work_id;
    current_exists := FOUND;
    observed_at := pg_catalog.clock_timestamp();
    IF NOT current_exists THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF current_row.token IS DISTINCT FROM p_token
       OR current_row.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR current_row.cycle IS DISTINCT FROM p_cycle
       OR current_row.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF current_row.state IS DISTINCT FROM 'running' THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='work is not running';
    END IF;
    IF current_row.cycle IS DISTINCT FROM 1 OR current_row.attempt_count IS NULL
       OR current_row.attempt_count < 1 OR current_row.attempt_count > 1000
       OR current_row.max_attempts IS NULL OR current_row.max_attempts < 1 OR current_row.max_attempts > 1000
       OR current_row.attempt_count > current_row.max_attempts
       OR current_row.runnable_version IS NULL OR current_row.runnable_version <= 0
       OR current_row.token IS NULL OR current_row.lease_until IS NULL
       OR current_row.dispatch_id IS NULL OR current_row.result IS NOT NULL
       OR current_row.success_origin IS NOT NULL OR current_row.completion_guard_id IS NOT NULL
       OR current_row.final_fence_at IS NOT NULL OR current_row.completion_result_digest IS NOT NULL
       OR current_row.resolution_operation_id IS NOT NULL OR current_row.terminal_resolution_operation_id IS NOT NULL
       OR current_row.attempt_work_id IS DISTINCT FROM p_work_id
       OR current_row.attempt_cycle IS DISTINCT FROM current_row.cycle
       OR current_row.attempt_ordinal IS DISTINCT FROM current_row.attempt_count
       OR current_row.attempt_dispatch_id IS DISTINCT FROM current_row.dispatch_id
       OR current_row.attempt_outcome IS DISTINCT FROM 'dispatched'
       OR current_row.attempt_evidence IS DISTINCT FROM ''::pg_catalog.bytea
       OR current_row.dispatch_root_xid IS NULL OR current_row.dispatch_root_xid <= '0'::pg_catalog.xid8
       OR modkit_events._instant_bytes(current_row.attempt_recorded_at) IS NULL
       OR modkit_events._instant_bytes(current_row.lease_until) IS NULL
       OR (current_row.deadline IS NOT NULL AND
          (modkit_events._instant_bytes(current_row.deadline) IS NULL OR current_row.lease_until > current_row.deadline)) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='inconsistent running dispatch';
    END IF;
    IF current_row.cancellation_requested IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work cancellation requested';
    END IF;
    IF current_row.deadline IS NOT NULL AND observed_at >= current_row.deadline THEN
        RAISE EXCEPTION USING ERRCODE='PZ009',MESSAGE='work deadline reached';
    END IF;
    IF observed_at >= current_row.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work lease expired';
    END IF;

    -- Every error propagates and aborts the provisional insertion. Only the
    -- captured persisted row is returned; E10 still owns the final locked fence.
    RETURN QUERY SELECT inserted_guard.guard_id,inserted_guard.work_id,inserted_guard.root_xid,
      inserted_guard.token,inserted_guard.ownership_revision,inserted_guard.cycle,
      inserted_guard.expected_attempt,inserted_guard.satisfied,inserted_guard.final_fence_at,
      inserted_guard.terminal_state,inserted_guard.result_digest;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e08(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

-- Segment6: private subtype storage and admission composition, SOURCE ONLY.
-- All behavior NOT_RUN. No E10/index/public producers/readers are added here.
CREATE FUNCTION modkit_events._protected_frame_valid(p_binding pg_catalog.bytea)
RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    fields pg_catalog.bytea[];
    optional_fields pg_catalog.int4[] := ARRAY[2,3,4,6,7]::pg_catalog.int4[];
    decoded pg_catalog.bytea[] := ARRAY[NULL,NULL,NULL,NULL,NULL]::pg_catalog.bytea[];
    raw_optional pg_catalog.bytea;
    valid_optional pg_catalog.bool;
    n pg_catalog.int4;
    size pg_catalog.int4;
    i pg_catalog.int4;
    j pg_catalog.int4;
    digit pg_catalog.int4;
    starts pg_catalog.int4[] := ARRAY[0,5,8,11,14,17,20]::pg_catalog.int4[];
    widths pg_catalog.int4[] := ARRAY[4,2,2,2,2,2,6]::pg_catalog.int4[];
    parts pg_catalog.int4[] := ARRAY[0,0,0,0,0,0,0]::pg_catalog.int4[];
    month_days pg_catalog.int4;
    expiry pg_catalog.timestamptz;
    state_value pg_catalog.text;
    cleanup_value pg_catalog.text;
BEGIN
    IF p_binding IS NULL THEN RETURN FALSE; END IF;
    n := pg_catalog.octet_length(p_binding);
    IF n < 1 OR n > 1048576 THEN RETURN FALSE; END IF;
    fields := modkit_events._record_fields(p_binding,pg_catalog.convert_to('protected-binding','UTF8'),10);
    IF fields IS NULL THEN RETURN FALSE; END IF;
    -- Select fixed text literals only after exact byte code comparisons.
    IF fields[1] = pg_catalog.convert_to('absent','UTF8') THEN state_value := 'absent';
    ELSIF fields[1] = pg_catalog.convert_to('present','UTF8') THEN state_value := 'present';
    ELSE RETURN FALSE;
    END IF;
    IF fields[5] = pg_catalog.convert_to('retain','UTF8') THEN cleanup_value := 'retain';
    ELSIF fields[5] = pg_catalog.convert_to('erase_after_terminal','UTF8') THEN cleanup_value := 'erase_after_terminal';
    ELSE RETURN FALSE;
    END IF;
    FOR i IN 1..5 LOOP
        raw_optional := fields[optional_fields[i]];
        valid_optional := FALSE;
        IF raw_optional = pg_catalog.decode('30','hex') THEN
            decoded[i] := NULL;
            valid_optional := TRUE;
        ELSE
            n := pg_catalog.octet_length(raw_optional);
            IF n < 9 THEN RETURN FALSE; END IF;
            IF pg_catalog.get_byte(raw_optional,0) <> 49 THEN RETURN FALSE; END IF;
            size := modkit_events._bounded_uint(raw_optional,1,8,1048576);
            IF size IS NULL THEN RETURN FALSE; END IF;
            IF size <> n - 9 THEN RETURN FALSE; END IF;
            decoded[i] := pg_catalog.substr(raw_optional,10,size);
            valid_optional := TRUE;
        END IF;
        IF valid_optional IS NOT TRUE THEN RETURN FALSE; END IF;
        IF raw_optional IS DISTINCT FROM modkit_events._optional_bytes(decoded[i]) THEN RETURN FALSE; END IF;
    END LOOP;
    IF decoded[1] IS NOT NULL THEN
        IF modkit_events._utf8_valid(decoded[1],256,TRUE) IS NOT TRUE THEN RETURN FALSE; END IF;
    END IF;
    IF decoded[2] IS NOT NULL THEN
        IF modkit_events._utf8_valid(decoded[2],256,TRUE) IS NOT TRUE THEN RETURN FALSE; END IF;
    END IF;
    IF decoded[3] IS NOT NULL THEN
        -- Exact27-byte YYYY-MM-DDTHH:MM:SS.ffffffZ, before any indexed access.
        IF pg_catalog.octet_length(decoded[3]) <> 27 THEN RETURN FALSE; END IF;
        IF pg_catalog.get_byte(decoded[3],4) <> 45 OR pg_catalog.get_byte(decoded[3],7) <> 45
           OR pg_catalog.get_byte(decoded[3],10) <> 84 OR pg_catalog.get_byte(decoded[3],13) <> 58
           OR pg_catalog.get_byte(decoded[3],16) <> 58 OR pg_catalog.get_byte(decoded[3],19) <> 46
           OR pg_catalog.get_byte(decoded[3],26) <> 90 THEN RETURN FALSE; END IF;
        FOR i IN 1..7 LOOP
            FOR j IN starts[i]..starts[i]+widths[i]-1 LOOP
                digit := pg_catalog.get_byte(decoded[3],j);
                IF digit < 48 OR digit > 57 THEN RETURN FALSE; END IF;
                parts[i] := parts[i] * 10 + digit - 48;
            END LOOP;
        END LOOP;
        IF parts[1] < 1 OR parts[1] > 9999 OR parts[2] < 1 OR parts[2] > 12
           OR parts[4] > 23 OR parts[5] > 59 OR parts[6] > 59
           OR parts[7] > 999999 THEN RETURN FALSE; END IF;
        IF parts[2] = 2 THEN
            month_days := 28;
            IF pg_catalog.mod(parts[1],4) = 0
               AND (pg_catalog.mod(parts[1],100) <> 0 OR pg_catalog.mod(parts[1],400) = 0) THEN
                month_days := 29;
            END IF;
        ELSIF parts[2] IN (4,6,9,11) THEN month_days := 30;
        ELSE month_days := 31;
        END IF;
        IF parts[3] < 1 OR parts[3] > month_days THEN RETURN FALSE; END IF;
        expiry := pg_catalog.make_timestamptz(parts[1],parts[2],parts[3],parts[4],parts[5],
            parts[6]::pg_catalog.float8 + parts[7]::pg_catalog.float8 / 1000000::pg_catalog.float8,
            'UTC'::pg_catalog.text);
        IF modkit_events._instant_bytes(expiry) IS DISTINCT FROM decoded[3] THEN RETURN FALSE; END IF;
    END IF;
    RETURN modkit_events._protected_valid(p_binding,state_value,decoded[4],decoded[5],decoded[1],decoded[2],
        expiry,fields[9],cleanup_value,fields[10]) IS TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._protected_frame_valid(pg_catalog.bytea) FROM PUBLIC;

CREATE TABLE modkit_events.job_payloads (
    job_work_id pg_catalog.uuid NOT NULL,
    job_application pg_catalog.bytea NOT NULL,
    job_tenant pg_catalog.bytea,
    job_owner pg_catalog.bytea,
    job_protected_binding pg_catalog.bytea NOT NULL,
    job_semantic_input pg_catalog.bytea NOT NULL,
    material_state pg_catalog.text NOT NULL,
    protected_sidecar pg_catalog.bytea,
    protected_reference pg_catalog.bytea,
    protected_codec pg_catalog.bytea,
    protected_key_version pg_catalog.bytea,
    protected_expires_at pg_catalog.timestamptz,
    protected_recovery_metadata pg_catalog.bytea NOT NULL,
    protected_cleanup_policy pg_catalog.text NOT NULL,
    projection_metadata pg_catalog.bytea NOT NULL,
    CONSTRAINT job_payloads_pkey PRIMARY KEY (job_work_id),
    CONSTRAINT job_payloads_work_fk FOREIGN KEY (job_work_id) REFERENCES modkit_events.work(work_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT NOT DEFERRABLE,
    CONSTRAINT job_payloads_application_valid CHECK (modkit_events._utf8_valid(job_application,256,TRUE) IS TRUE),
    CONSTRAINT job_payloads_tenant_valid CHECK (job_tenant IS NULL OR modkit_events._utf8_valid(job_tenant,256,TRUE) IS TRUE),
    CONSTRAINT job_payloads_owner_valid CHECK (job_owner IS NULL OR modkit_events._utf8_valid(job_owner,256,TRUE) IS TRUE),
    CONSTRAINT job_payloads_binding_size CHECK (pg_catalog.octet_length(job_protected_binding) BETWEEN 1 AND 1048576),
    CONSTRAINT job_payloads_semantic_size CHECK (pg_catalog.octet_length(job_semantic_input) BETWEEN 1 AND 1048576),
    CONSTRAINT job_payloads_semantic_object CHECK ((CASE WHEN pg_catalog.octet_length(job_semantic_input) > 0
        THEN pg_catalog.get_byte(job_semantic_input,0) = 111
             AND modkit_events._j_nodes(job_semantic_input,0,262144) IS NOT NULL ELSE FALSE END) IS TRUE),
    CONSTRAINT job_payloads_material_state CHECK (pg_catalog.convert_to(material_state,'UTF8')
        IN (pg_catalog.convert_to('absent','UTF8'),pg_catalog.convert_to('present','UTF8'))),
    CONSTRAINT job_payloads_sidecar_size CHECK (protected_sidecar IS NULL OR pg_catalog.octet_length(protected_sidecar) BETWEEN 1 AND 1048576),
    CONSTRAINT job_payloads_reference_size CHECK (protected_reference IS NULL OR pg_catalog.octet_length(protected_reference) BETWEEN 1 AND 1048576),
    CONSTRAINT job_payloads_codec_valid CHECK (protected_codec IS NULL OR modkit_events._utf8_valid(protected_codec,256,TRUE) IS TRUE),
    CONSTRAINT job_payloads_key_valid CHECK (protected_key_version IS NULL OR modkit_events._utf8_valid(protected_key_version,256,TRUE) IS TRUE),
    CONSTRAINT job_payloads_expiry_valid CHECK (protected_expires_at IS NULL OR modkit_events._instant_bytes(protected_expires_at) IS NOT NULL),
    CONSTRAINT job_payloads_recovery_size CHECK (pg_catalog.octet_length(protected_recovery_metadata) BETWEEN 0 AND 1048576),
    CONSTRAINT job_payloads_cleanup_policy CHECK (pg_catalog.convert_to(protected_cleanup_policy,'UTF8')
        IN (pg_catalog.convert_to('retain','UTF8'),pg_catalog.convert_to('erase_after_terminal','UTF8'))),
    CONSTRAINT job_payloads_projection_size CHECK (pg_catalog.octet_length(projection_metadata) BETWEEN 1 AND 1048576),
    CONSTRAINT job_payloads_projection_object CHECK ((CASE WHEN pg_catalog.octet_length(projection_metadata) > 0
        THEN pg_catalog.get_byte(projection_metadata,0) = 111
             AND modkit_events._j_nodes(projection_metadata,0,262144) IS NOT NULL ELSE FALSE END) IS TRUE),
    CONSTRAINT job_payloads_material_binding CHECK (modkit_events._protected_valid(
        job_protected_binding,material_state,protected_sidecar,protected_reference,protected_codec,
        protected_key_version,protected_expires_at,protected_recovery_metadata,protected_cleanup_policy,projection_metadata) IS TRUE)
);
REVOKE ALL ON TABLE modkit_events.job_payloads FROM PUBLIC;

CREATE FUNCTION modkit_events._job_payload_record_check()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE w modkit_events.work%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='subtype mutation rejected';
    END IF;
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF NEW.job_work_id IS NULL THEN RETURN NEW; END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored
        WHERE stored.work_id = NEW.job_work_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    -- Separate READ COMMITTED statement after any wait; lock remains held.
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id = NEW.job_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('job','UTF8')
       OR w.subscription_id IS NOT NULL
       OR w.namespace IS DISTINCT FROM pg_catalog.convert_to('jobs','UTF8')
       OR NEW.job_work_id IS DISTINCT FROM w.work_id
       OR NEW.job_application IS DISTINCT FROM w.scope_application
       OR NEW.job_tenant IS DISTINCT FROM w.scope_tenant
       OR NEW.job_owner IS DISTINCT FROM w.scope_owner
       OR NEW.job_semantic_input IS DISTINCT FROM w.semantic_input
       OR NEW.job_protected_binding IS DISTINCT FROM w.protected_binding THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF modkit_events._scope_valid(w.scope_evidence,NEW.job_application,NEW.job_tenant,NEW.job_owner) IS NOT TRUE
       OR modkit_events._intent_valid(w.kind,w.subscription_id,w.namespace,w.command_type,
           w.scope_evidence,w.idempotency_key,w.canonical_version,w.schema_version_decimal,
           w.scope_application,w.scope_tenant,w.scope_owner,w.intent_evidence,w.semantic_input,w.replay_input,
           w.protected_binding,w.replay_policy,w.max_attempts,w.deadline,w.original_available_at) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF EXISTS (SELECT 1 FROM modkit_events.inbox AS opposite WHERE opposite.work_id = w.work_id) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    -- Local typed material CHECKs follow. Do not relocate their error stage.
    RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._job_payload_record_check() FROM PUBLIC;
CREATE TRIGGER job_payload_record_check BEFORE INSERT OR UPDATE OR DELETE ON modkit_events.job_payloads
    FOR EACH ROW EXECUTE FUNCTION modkit_events._job_payload_record_check();

CREATE FUNCTION modkit_events._inbox_record_check()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp
AS $body$
DECLARE
    w modkit_events.work%ROWTYPE;
    envelope pg_catalog.bytea;
    fields pg_catalog.bytea[];
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='subtype mutation rejected';
    END IF;
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF NEW.work_id IS NULL THEN RETURN NEW; END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored
        WHERE stored.work_id = NEW.work_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id = NEW.work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('inbox','UTF8')
       OR w.subscription_id IS NULL OR NEW.subscription_id IS DISTINCT FROM w.subscription_id
       OR NEW.work_id IS DISTINCT FROM w.work_id OR NEW.replay_input IS DISTINCT FROM w.replay_input THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    -- Identity read only: E03 must acquire subscription BEFORE work itself.
    IF NOT EXISTS (SELECT 1 FROM modkit_events.subscriptions AS parent
                   WHERE parent.subscription_id = w.subscription_id) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF modkit_events._intent_valid(w.kind,w.subscription_id,w.namespace,w.command_type,
        w.scope_evidence,w.idempotency_key,w.canonical_version,w.schema_version_decimal,
        w.scope_application,w.scope_tenant,w.scope_owner,w.intent_evidence,w.semantic_input,w.replay_input,
        w.protected_binding,w.replay_policy,w.max_attempts,w.deadline,w.original_available_at) IS NOT TRUE
       OR modkit_events._protected_frame_valid(w.protected_binding) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    envelope := modkit_events._event_replay_frame(NEW.replay_input);
    IF envelope IS NULL OR envelope IS DISTINCT FROM NEW.envelope_evidence
       OR envelope IS DISTINCT FROM w.semantic_input THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    fields := modkit_events._record_fields(NEW.envelope_evidence,pg_catalog.convert_to('event-envelope','UTF8'),5);
    IF fields IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF fields[1] IS DISTINCT FROM NEW.event_id OR fields[2] IS DISTINCT FROM w.command_type
       OR fields[3] IS DISTINCT FROM w.schema_version_decimal THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    IF EXISTS (SELECT 1 FROM modkit_events.job_payloads AS opposite WHERE opposite.job_work_id = w.work_id) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored composition';
    END IF;
    RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._inbox_record_check() FROM PUBLIC;
CREATE TRIGGER inbox_record_check BEFORE INSERT OR UPDATE OR DELETE ON modkit_events.inbox
    FOR EACH ROW EXECUTE FUNCTION modkit_events._inbox_record_check();

CREATE FUNCTION modkit_events._work_admission_immutable()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp
AS $body$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work admission mutation rejected';
    END IF;
    IF ROW(NEW.work_id,pg_catalog.convert_to(NEW.kind,'UTF8'),NEW.subscription_id,NEW.namespace,NEW.command_type,
        NEW.schema_version_decimal,NEW.canonical_version,NEW.scope_evidence,NEW.scope_application,
        NEW.scope_tenant,NEW.scope_owner,NEW.idempotency_key,NEW.intent_evidence,NEW.semantic_input,
        NEW.replay_input,NEW.protected_binding,pg_catalog.convert_to(NEW.replay_policy,'UTF8'),NEW.max_attempts,
        NEW.deadline,NEW.original_available_at,NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.work_id,pg_catalog.convert_to(OLD.kind,'UTF8'),OLD.subscription_id,OLD.namespace,OLD.command_type,
        OLD.schema_version_decimal,OLD.canonical_version,OLD.scope_evidence,OLD.scope_application,
        OLD.scope_tenant,OLD.scope_owner,OLD.idempotency_key,OLD.intent_evidence,OLD.semantic_input,
        OLD.replay_input,OLD.protected_binding,pg_catalog.convert_to(OLD.replay_policy,'UTF8'),OLD.max_attempts,
        OLD.deadline,OLD.original_available_at,OLD.created_at) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work admission mutation rejected';
    END IF;
    RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events._work_admission_immutable() FROM PUBLIC;
CREATE TRIGGER work_admission_immutable BEFORE UPDATE OR DELETE ON modkit_events.work
    FOR EACH ROW EXECUTE FUNCTION modkit_events._work_admission_immutable();

-- Segment7: final locked completion. Source text only; behavior NOT_RUN.
CREATE INDEX work_history_complete_lookup ON modkit_events.work_history(work_id,cycle,attempt,history_id)
    WHERE transition COLLATE pg_catalog."C" = 'complete'::pg_catalog.text COLLATE pg_catalog."C";

CREATE FUNCTION modkit_events.e10(
    p_guard_id pg_catalog.uuid,
    p_work_id pg_catalog.uuid,
    p_root_xid pg_catalog.xid8,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4,
    p_result pg_catalog.bytea
)
RETURNS TABLE(ok pg_catalog.bool)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    actual_root pg_catalog.xid8;
    discovery modkit_events.work%ROWTYPE;
    w modkit_events.work%ROWTYPE;
    g modkit_events.finalization_guards%ROWTYPE;
    s modkit_events.subscriptions%ROWTYPE;
    j modkit_events.job_payloads%ROWTYPE;
    i modkit_events.inbox%ROWTYPE;
    a modkit_events.attempts%ROWTYPE;
    is_job pg_catalog.bool;
    final_time pg_catalog.timestamptz;
    successor pg_catalog.int8;
    result_digest_value pg_catalog.bytea;
    envelope pg_catalog.bytea;
    fields pg_catalog.bytea[];
    affected pg_catalog.int8;
BEGIN
    -- No assigning initializer or relation lookup precedes the profile check.
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_guard_id IS NULL OR p_work_id IS NULL OR p_root_xid IS NULL OR p_token IS NULL
       OR p_ownership_revision IS NULL OR p_cycle IS NULL OR p_expected_attempt IS NULL OR p_result IS NULL
       OR p_root_xid <= '0'::pg_catalog.xid8 OR p_ownership_revision <= 0 OR p_cycle <> 1
       OR p_expected_attempt < 0 OR p_expected_attempt > 1000 OR pg_catalog.octet_length(p_result) > 1048576 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid completion arguments';
    END IF;
    actual_root := pg_catalog.pg_current_xact_id();
    IF p_root_xid IS DISTINCT FROM actual_root THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='guard does not belong to current root';
    END IF;
    -- Standalone early guard lookup deliberately precedes missing-work lookup.
    SELECT stored.* INTO g FROM modkit_events.finalization_guards AS stored WHERE stored.guard_id=p_guard_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='invalid completion guard';
    END IF;
    IF g.guard_id IS DISTINCT FROM p_guard_id OR g.work_id IS DISTINCT FROM p_work_id
       OR g.root_xid IS DISTINCT FROM p_root_xid OR g.token IS DISTINCT FROM p_token
       OR g.ownership_revision IS DISTINCT FROM p_ownership_revision OR g.cycle IS DISTINCT FROM p_cycle
       OR g.expected_attempt IS DISTINCT FROM p_expected_attempt OR g.satisfied IS DISTINCT FROM FALSE
       OR g.final_fence_at IS NOT NULL OR g.terminal_state IS NOT NULL OR g.result_digest IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='invalid completion guard';
    END IF;
    SELECT stored.* INTO discovery FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF pg_catalog.convert_to(discovery.kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
        is_job := TRUE;
        IF discovery.subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSIF pg_catalog.convert_to(discovery.kind,'UTF8') = pg_catalog.convert_to('inbox','UTF8') THEN
        is_job := FALSE;
        IF discovery.subscription_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;
    IF NOT is_job THEN
        PERFORM stored.subscription_id FROM modkit_events.subscriptions AS stored
            WHERE stored.subscription_id=discovery.subscription_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
        END IF;
        SELECT stored.* INTO s FROM modkit_events.subscriptions AS stored
            WHERE stored.subscription_id=discovery.subscription_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
        END IF;
    END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(discovery.kind,'UTF8')
       OR w.subscription_id IS DISTINCT FROM discovery.subscription_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work identity changed during acquisition';
    END IF;
    PERFORM stored.guard_id FROM modkit_events.finalization_guards AS stored
        WHERE stored.guard_id=p_guard_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='invalid completion guard';
    END IF;
    SELECT stored.* INTO g FROM modkit_events.finalization_guards AS stored WHERE stored.guard_id=p_guard_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='invalid completion guard';
    END IF;
    IF g.guard_id IS DISTINCT FROM p_guard_id OR g.work_id IS DISTINCT FROM p_work_id
       OR g.root_xid IS DISTINCT FROM p_root_xid OR g.token IS DISTINCT FROM p_token
       OR g.ownership_revision IS DISTINCT FROM p_ownership_revision OR g.cycle IS DISTINCT FROM p_cycle
       OR g.expected_attempt IS DISTINCT FROM p_expected_attempt OR g.satisfied IS DISTINCT FROM FALSE
       OR g.final_fence_at IS NOT NULL OR g.terminal_state IS NOT NULL OR g.result_digest IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ008',MESSAGE='invalid completion guard';
    END IF;
    IF w.token IS DISTINCT FROM p_token OR w.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR w.cycle IS DISTINCT FROM p_cycle OR w.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF pg_catalog.convert_to(w.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('running','UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='work is not running';
    END IF;
    IF is_job THEN
        SELECT stored.* INTO j FROM modkit_events.job_payloads AS stored
            WHERE stored.job_work_id=p_work_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing job subtype';
        END IF;
        IF EXISTS(SELECT 1 FROM modkit_events.inbox AS opposite WHERE opposite.work_id=p_work_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='extra inbox subtype';
        END IF;
    ELSE
        SELECT stored.* INTO i FROM modkit_events.inbox AS stored
            WHERE stored.work_id=p_work_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing inbox subtype';
        END IF;
        IF EXISTS(SELECT 1 FROM modkit_events.job_payloads AS opposite WHERE opposite.job_work_id=p_work_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='extra job subtype';
        END IF;
    END IF;
    SELECT stored.* INTO a FROM modkit_events.attempts AS stored
        WHERE stored.work_id=p_work_id AND stored.cycle=w.cycle AND stored.attempt=w.attempt_count FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing current attempt';
    END IF;
    IF a.work_id IS DISTINCT FROM p_work_id OR a.cycle IS DISTINCT FROM w.cycle
       OR a.attempt IS DISTINCT FROM w.attempt_count OR a.dispatch_id IS DISTINCT FROM w.dispatch_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid current dispatch identity';
    END IF;
    -- All entity acquisitions have finished. Remaining validation uses locals
    -- and pure byte primitives only. Physical COMMIT freshness is not promised.
    final_time := pg_catalog.clock_timestamp();
    IF (pg_catalog.convert_to(w.replay_policy,'UTF8') IN
          (pg_catalog.convert_to('disabled','UTF8'),pg_catalog.convert_to('application_safe','UTF8'))) IS NOT TRUE
       OR modkit_events._scope_valid(w.scope_evidence,w.scope_application,w.scope_tenant,w.scope_owner) IS NOT TRUE
       OR modkit_events._intent_valid(w.kind,w.subscription_id,w.namespace,w.command_type,
           w.scope_evidence,w.idempotency_key,w.canonical_version,w.schema_version_decimal,
           w.scope_application,w.scope_tenant,w.scope_owner,w.intent_evidence,w.semantic_input,w.replay_input,
           w.protected_binding,w.replay_policy,w.max_attempts,w.deadline,w.original_available_at) IS NOT TRUE
       OR modkit_events._protected_frame_valid(w.protected_binding) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid neutral work composition';
    END IF;
    IF is_job THEN
        IF w.subscription_id IS NOT NULL OR w.namespace IS DISTINCT FROM pg_catalog.convert_to('jobs','UTF8')
           OR j.job_work_id IS DISTINCT FROM w.work_id OR j.job_application IS DISTINCT FROM w.scope_application
           OR j.job_tenant IS DISTINCT FROM w.scope_tenant OR j.job_owner IS DISTINCT FROM w.scope_owner
           OR j.job_semantic_input IS DISTINCT FROM w.semantic_input OR j.job_protected_binding IS DISTINCT FROM w.protected_binding
           OR modkit_events._scope_valid(w.scope_evidence,j.job_application,j.job_tenant,j.job_owner) IS NOT TRUE
           OR modkit_events._protected_valid(j.job_protected_binding,j.material_state,j.protected_sidecar,
               j.protected_reference,j.protected_codec,j.protected_key_version,j.protected_expires_at,
               j.protected_recovery_metadata,j.protected_cleanup_policy,j.projection_metadata) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid job composition';
        END IF;
    ELSE
        IF w.subscription_id IS NULL OR s.subscription_id IS DISTINCT FROM w.subscription_id
           OR i.work_id IS DISTINCT FROM w.work_id OR i.subscription_id IS DISTINCT FROM w.subscription_id
           OR i.replay_input IS DISTINCT FROM w.replay_input
           OR modkit_events._utf8_valid(i.event_id,256,TRUE) IS NOT TRUE
           OR i.event_digest IS DISTINCT FROM pg_catalog.sha256(i.event_id)
           OR modkit_events._utf8_valid(s.subscription_id,256,TRUE) IS NOT TRUE
           OR s.manifest IS NULL OR pg_catalog.octet_length(s.manifest)>1048576
           OR modkit_events._utf8_valid(s.consumer_group,256,TRUE) IS NOT TRUE
           OR s.nonterminal_count IS NULL OR s.nonterminal_count <= 0 OR s.capacity IS NULL
           OR s.capacity <= 0 OR s.nonterminal_count > s.capacity
           OR modkit_events._instant_bytes(s.created_at) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox composition';
        END IF;
        envelope := modkit_events._event_replay_frame(i.replay_input);
        IF envelope IS NULL OR envelope IS DISTINCT FROM i.envelope_evidence OR envelope IS DISTINCT FROM w.semantic_input THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope';
        END IF;
        fields := modkit_events._record_fields(i.envelope_evidence,pg_catalog.convert_to('event-envelope','UTF8'),5);
        IF fields IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope';
        END IF;
        IF fields[1] IS DISTINCT FROM i.event_id OR fields[2] IS DISTINCT FROM w.command_type
           OR fields[3] IS DISTINCT FROM w.schema_version_decimal THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope identity';
        END IF;
    END IF;
    IF w.cycle IS DISTINCT FROM 1 OR w.attempt_count IS NULL OR w.attempt_count < 1 OR w.attempt_count > 1000
       OR w.max_attempts IS NULL OR w.max_attempts < 1 OR w.max_attempts > 1000 OR w.attempt_count > w.max_attempts
       OR w.runnable_version IS NULL OR w.runnable_version <= 0
       OR w.schema_version_decimal IS DISTINCT FROM pg_catalog.convert_to(w.runnable_version::pg_catalog.text,'UTF8')
       OR w.token IS NULL OR w.ownership_revision IS NULL OR w.ownership_revision <= 0 OR w.lease_until IS NULL
       OR w.dispatch_id IS NULL OR w.result IS NOT NULL OR w.success_origin IS NOT NULL
       OR w.completion_guard_id IS NOT NULL OR w.final_fence_at IS NOT NULL OR w.completion_result_digest IS NOT NULL
       OR w.resolution_operation_id IS NOT NULL OR w.terminal_resolution_operation_id IS NOT NULL
       OR pg_catalog.convert_to(a.outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('dispatched','UTF8')
       OR a.evidence IS DISTINCT FROM ''::pg_catalog.bytea
       OR a.dispatch_root_xid IS NULL OR a.dispatch_root_xid <= '0'::pg_catalog.xid8
       OR modkit_events._instant_bytes(a.recorded_at) IS NULL
       OR modkit_events._utf8_valid(a.effect_id,256,TRUE) IS NOT TRUE
       OR a.request_evidence IS NULL OR pg_catalog.octet_length(a.request_evidence)>1048576
       OR (a.provider_key_reference IS NOT NULL AND modkit_events._utf8_valid(a.provider_key_reference,256,TRUE) IS NOT TRUE)
       OR modkit_events._instant_bytes(w.lease_until) IS NULL
       OR modkit_events._instant_bytes(w.available_at) IS NULL
       OR modkit_events._instant_bytes(w.created_at) IS NULL
       OR modkit_events._instant_bytes(w.updated_at) IS NULL
       OR modkit_events._instant_bytes(final_time) IS NULL
       OR (w.deadline IS NOT NULL AND
           (modkit_events._instant_bytes(w.deadline) IS NULL OR w.lease_until>w.deadline)) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='inconsistent running dispatch';
    END IF;
    IF w.ownership_revision=9223372036854775807::pg_catalog.int8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='ownership revision exhausted';
    END IF;
    IF w.cancellation_requested IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work cancellation requested';
    END IF;
    IF w.deadline IS NOT NULL AND final_time>=w.deadline THEN
        RAISE EXCEPTION USING ERRCODE='PZ009',MESSAGE='work deadline reached';
    END IF;
    IF final_time>=w.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work lease expired';
    END IF;
    successor := w.ownership_revision+1;
    result_digest_value := pg_catalog.sha256(p_result);
    UPDATE modkit_events.attempts AS stored SET outcome='succeeded',evidence=''::pg_catalog.bytea
        WHERE stored.work_id=p_work_id AND stored.cycle=w.cycle AND stored.attempt=w.attempt_count;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='attempt update cardinality'; END IF;
    UPDATE modkit_events.work AS stored SET state='succeeded',token=NULL,lease_until=NULL,
        ownership_revision=successor,result=p_result,success_origin='guarded',completion_guard_id=p_guard_id,
        final_fence_at=final_time,completion_result_digest=result_digest_value,
        resolution_operation_id=NULL,terminal_resolution_operation_id=NULL,updated_at=final_time
        WHERE stored.work_id=p_work_id;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work update cardinality'; END IF;
    INSERT INTO modkit_events.work_history(work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(p_work_id,w.cycle,w.attempt_count,'complete','complete',NULL,successor,''::pg_catalog.bytea,final_time);
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='history insertion cardinality'; END IF;
    IF NOT is_job THEN
        UPDATE modkit_events.subscriptions AS stored SET nonterminal_count=s.nonterminal_count-1
            WHERE stored.subscription_id=s.subscription_id;
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='subscription update cardinality'; END IF;
    END IF;
    UPDATE modkit_events.finalization_guards AS stored SET satisfied=TRUE,terminal_state='succeeded',
        final_fence_at=final_time,result_digest=result_digest_value WHERE stored.guard_id=p_guard_id;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='guard update cardinality'; END IF;
    RETURN QUERY SELECT TRUE::pg_catalog.bool;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e10(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.xid8,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.bytea) FROM PUBLIC;

-- Segment8: coherent protected work reader, AB-E15-1. Runtime qualification
-- remains separate. All relational evidence is captured by ONE statement.
CREATE FUNCTION modkit_events.e15(p_work_id pg_catalog.uuid)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    captured pg_catalog.record;
    w modkit_events.work%ROWTYPE;
    j modkit_events.job_payloads%ROWTYPE;
    i modkit_events.inbox%ROWTYPE;
    s modkit_events.subscriptions%ROWTYPE;
    a modkit_events.attempts%ROWTYPE;
    g modkit_events.finalization_guards%ROWTYPE;
    r modkit_events.mutation_operations%ROWTYPE;
    h modkit_events.work_history%ROWTYPE;
    complete_rows modkit_events.work_history[];
    reconcile_rows modkit_events.work_history[];
    is_job pg_catalog.bool;
    owned pg_catalog.bool;
    guarded pg_catalog.bool;
    has_resolution pg_catalog.bool;
    envelope pg_catalog.bytea;
    fields pg_catalog.bytea[];
    reconciliation_code pg_catalog.text;
    reconciliation_outcome pg_catalog.text;
    attempt_outcome pg_catalog.text;
    successor pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid work reader arguments';
    END IF;
    -- PK sentinels, not composite row-null predicates. Both subtype joins use
    -- requested ID even if work is absent. Latest attempt survives pointer clear.
    SELECT wr AS work_row, jr AS job_row, ir AS inbox_row, sr AS subscription_row,
           ar AS attempt_row, gr AS guard_row, rr AS resolution_row,
           wr.work_id IS NOT NULL AS work_present, jr.job_work_id IS NOT NULL AS job_present,
           ir.work_id IS NOT NULL AS inbox_present, sr.subscription_id IS NOT NULL AS subscription_present,
           ar.work_id IS NOT NULL AS attempt_present, gr.guard_id IS NOT NULL AS guard_present,
           rr.operation_id IS NOT NULL AS operation_present,
           ch.items AS complete_items, rh.items AS reconcile_items
      INTO captured
      FROM (VALUES(p_work_id)) AS requested(id)
      LEFT JOIN modkit_events.work AS wr ON wr.work_id=requested.id
      LEFT JOIN modkit_events.job_payloads AS jr ON jr.job_work_id=requested.id
      LEFT JOIN modkit_events.inbox AS ir ON ir.work_id=requested.id
      LEFT JOIN modkit_events.subscriptions AS sr ON sr.subscription_id=wr.subscription_id
      LEFT JOIN modkit_events.attempts AS ar
        ON wr.attempt_count>0 AND ar.work_id=wr.work_id AND ar.cycle=wr.cycle AND ar.attempt=wr.attempt_count
      LEFT JOIN modkit_events.finalization_guards AS gr ON gr.guard_id=wr.completion_guard_id
      LEFT JOIN modkit_events.mutation_operations AS rr ON rr.operation_id=wr.terminal_resolution_operation_id
      LEFT JOIN LATERAL (
          SELECT ARRAY(SELECT hist FROM modkit_events.work_history AS hist
                       WHERE hist.work_id=wr.work_id AND hist.cycle=wr.cycle AND hist.attempt=wr.attempt_count
                         AND hist.transition COLLATE pg_catalog."C" = 'complete' COLLATE pg_catalog."C"
                       ORDER BY hist.history_id LIMIT 2) AS items
      ) AS ch ON TRUE
      LEFT JOIN LATERAL (
          SELECT ARRAY(SELECT hist FROM modkit_events.work_history AS hist
                       WHERE wr.terminal_resolution_operation_id IS NOT NULL
                         AND hist.work_id=wr.work_id AND hist.cycle=wr.cycle AND hist.attempt=wr.attempt_count
                         AND hist.transition COLLATE pg_catalog."C" =
                             (CASE wr.state COLLATE pg_catalog."C"
                                WHEN 'succeeded' THEN 'reconcile_success'
                                WHEN 'failed' THEN 'reconcile_rejection'
                                WHEN 'cancelled' THEN 'reconcile_cancelled'
                              END) COLLATE pg_catalog."C"
                       ORDER BY hist.history_id LIMIT 2) AS items
      ) AS rh ON TRUE;
    -- No relation access below: validators are existing immutable byte/time
    -- functions. RETURN QUERY projects captured locals only.
    IF NOT captured.work_present THEN
        IF captured.job_present OR captured.inbox_present THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='orphan work subtype';
        END IF;
        RETURN;
    END IF;
    w:=captured.work_row; j:=captured.job_row; i:=captured.inbox_row;
    s:=captured.subscription_row; a:=captured.attempt_row; g:=captured.guard_row;
    r:=captured.resolution_row; complete_rows:=captured.complete_items; reconcile_rows:=captured.reconcile_items;
    IF pg_catalog.convert_to(w.kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
        is_job:=TRUE;
    ELSIF pg_catalog.convert_to(w.kind,'UTF8') = pg_catalog.convert_to('inbox','UTF8') THEN
        is_job:=FALSE;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;
    IF w.work_id IS DISTINCT FROM p_work_id
       OR (pg_catalog.convert_to(w.replay_policy,'UTF8') IN
           (pg_catalog.convert_to('disabled','UTF8'),pg_catalog.convert_to('application_safe','UTF8'))) IS NOT TRUE
       OR modkit_events._scope_valid(w.scope_evidence,w.scope_application,w.scope_tenant,w.scope_owner) IS NOT TRUE
       OR modkit_events._intent_valid(w.kind,w.subscription_id,w.namespace,w.command_type,
           w.scope_evidence,w.idempotency_key,w.canonical_version,w.schema_version_decimal,
           w.scope_application,w.scope_tenant,w.scope_owner,w.intent_evidence,w.semantic_input,w.replay_input,
           w.protected_binding,w.replay_policy,w.max_attempts,w.deadline,w.original_available_at) IS NOT TRUE
       OR modkit_events._protected_frame_valid(w.protected_binding) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid neutral work composition';
    END IF;
    IF (w.state COLLATE pg_catalog."C" IN
        ('queued','claimed','running','retry_waiting','succeeded','failed','expired','cancelled','blocked_schema','held')) IS NOT TRUE
       OR w.cycle IS DISTINCT FROM 1 OR w.attempt_count IS NULL OR w.attempt_count<0
       OR w.attempt_count>w.max_attempts OR w.ownership_revision IS NULL OR w.ownership_revision<0
       OR w.cancellation_requested IS NULL
       OR (w.cancellation_requested AND w.state COLLATE pg_catalog."C" IN
           ('queued','claimed','running','retry_waiting','blocked_schema'))
       OR (w.runnable_version IS NOT NULL AND (w.runnable_version<=0 OR w.schema_version_decimal IS DISTINCT FROM
           pg_catalog.convert_to(w.runnable_version::pg_catalog.text,'UTF8')))
       OR (w.state COLLATE pg_catalog."C" IN ('queued','claimed','running','retry_waiting') AND w.runnable_version IS NULL)
       OR (w.state COLLATE pg_catalog."C" = 'claimed' AND w.attempt_count>=w.max_attempts)
       OR modkit_events._instant_bytes(w.available_at) IS NULL
       OR modkit_events._instant_bytes(w.created_at) IS NULL OR modkit_events._instant_bytes(w.updated_at) IS NULL
       OR (w.deadline IS NOT NULL AND modkit_events._instant_bytes(w.deadline) IS NULL)
       OR (w.lease_until IS NOT NULL AND modkit_events._instant_bytes(w.lease_until) IS NULL)
       OR (w.final_fence_at IS NOT NULL AND modkit_events._instant_bytes(w.final_fence_at) IS NULL)
       OR (w.deadline IS NOT NULL AND w.lease_until IS NOT NULL AND w.lease_until>w.deadline)
       OR (w.result IS NOT NULL AND pg_catalog.octet_length(w.result)>1048576) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work state';
    END IF;
    owned:=w.state COLLATE pg_catalog."C" IN ('claimed','running');
    IF owned IS DISTINCT FROM (w.token IS NOT NULL) OR owned IS DISTINCT FROM (w.lease_until IS NOT NULL)
       OR (owned AND w.ownership_revision<=0)
       OR (w.state COLLATE pg_catalog."C" IN ('queued','claimed','retry_waiting','blocked_schema') AND w.dispatch_id IS NOT NULL)
       OR (w.state COLLATE pg_catalog."C" IN ('running','held','succeeded') AND (w.dispatch_id IS NULL OR w.attempt_count<1))
       OR (w.dispatch_id IS NOT NULL AND w.attempt_count<1) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work ownership';
    END IF;
    IF is_job THEN
        IF NOT captured.job_present OR captured.inbox_present OR w.subscription_id IS NOT NULL
           OR w.namespace IS DISTINCT FROM pg_catalog.convert_to('jobs','UTF8')
           OR j.job_work_id IS DISTINCT FROM w.work_id OR j.job_application IS DISTINCT FROM w.scope_application
           OR j.job_tenant IS DISTINCT FROM w.scope_tenant OR j.job_owner IS DISTINCT FROM w.scope_owner
           OR j.job_semantic_input IS DISTINCT FROM w.semantic_input OR j.job_protected_binding IS DISTINCT FROM w.protected_binding
           OR modkit_events._scope_valid(w.scope_evidence,j.job_application,j.job_tenant,j.job_owner) IS NOT TRUE
           OR modkit_events._protected_valid(j.job_protected_binding,j.material_state,j.protected_sidecar,
               j.protected_reference,j.protected_codec,j.protected_key_version,j.protected_expires_at,
               j.protected_recovery_metadata,j.protected_cleanup_policy,j.projection_metadata) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid job composition';
        END IF;
    ELSE
        IF NOT captured.inbox_present OR captured.job_present OR NOT captured.subscription_present
           OR w.subscription_id IS NULL OR s.subscription_id IS DISTINCT FROM w.subscription_id
           OR i.work_id IS DISTINCT FROM w.work_id OR i.subscription_id IS DISTINCT FROM w.subscription_id
           OR i.replay_input IS DISTINCT FROM w.replay_input
           OR modkit_events._utf8_valid(i.event_id,256,TRUE) IS NOT TRUE
           OR i.event_digest IS DISTINCT FROM pg_catalog.sha256(i.event_id)
           OR modkit_events._utf8_valid(s.subscription_id,256,TRUE) IS NOT TRUE
           OR modkit_events._utf8_valid(s.consumer_group,256,TRUE) IS NOT TRUE
           OR s.manifest IS NULL OR pg_catalog.octet_length(s.manifest)>1048576
           OR s.capacity IS NULL OR s.capacity<=0 OR s.nonterminal_count IS NULL
           OR s.nonterminal_count<0 OR s.nonterminal_count>s.capacity
           OR modkit_events._instant_bytes(s.created_at) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox composition';
        END IF;
        envelope:=modkit_events._event_replay_frame(i.replay_input);
        IF envelope IS NULL OR envelope IS DISTINCT FROM i.envelope_evidence OR envelope IS DISTINCT FROM w.semantic_input THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope';
        END IF;
        fields:=modkit_events._record_fields(i.envelope_evidence,pg_catalog.convert_to('event-envelope','UTF8'),5);
        IF fields IS NULL THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope'; END IF;
        IF fields[1] IS DISTINCT FROM i.event_id OR fields[2] IS DISTINCT FROM w.command_type
           OR fields[3] IS DISTINCT FROM w.schema_version_decimal THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid inbox envelope identity';
        END IF;
    END IF;
    IF w.attempt_count>0 THEN
        IF NOT captured.attempt_present OR a.work_id IS DISTINCT FROM w.work_id OR a.cycle IS DISTINCT FROM w.cycle
           OR a.attempt IS DISTINCT FROM w.attempt_count OR a.dispatch_id IS NULL
           OR (w.dispatch_id IS NOT NULL AND a.dispatch_id IS DISTINCT FROM w.dispatch_id)
           OR a.dispatch_root_xid IS NULL OR a.dispatch_root_xid<='0'::pg_catalog.xid8
           OR modkit_events._instant_bytes(a.recorded_at) IS NULL
           OR modkit_events._utf8_valid(a.effect_id,256,TRUE) IS NOT TRUE
           OR a.request_evidence IS NULL OR pg_catalog.octet_length(a.request_evidence)>1048576
           OR (a.provider_key_reference IS NOT NULL AND modkit_events._utf8_valid(a.provider_key_reference,256,TRUE) IS NOT TRUE)
           OR a.evidence IS NULL OR pg_catalog.octet_length(a.evidence)>1048576 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid latest dispatch identity';
        END IF;
        IF w.dispatch_id IS NULL THEN
            IF (a.outcome COLLATE pg_catalog."C" IN ('failed','safe_retry')) IS NOT TRUE THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unresolved prior dispatch';
            END IF;
        ELSIF w.state COLLATE pg_catalog."C" = 'running' THEN
            IF pg_catalog.convert_to(a.outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('dispatched','UTF8')
               OR a.evidence IS DISTINCT FROM ''::pg_catalog.bytea THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid running dispatch';
            END IF;
        ELSIF w.state COLLATE pg_catalog."C" = 'held' THEN
            IF (a.outcome COLLATE pg_catalog."C" IN ('uncertain','cancelled_unresolved')) IS NOT TRUE
               OR (a.outcome COLLATE pg_catalog."C" = 'cancelled_unresolved' AND a.evidence IS DISTINCT FROM ''::pg_catalog.bytea) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid held dispatch';
            END IF;
        ELSIF w.state COLLATE pg_catalog."C" IN ('succeeded','failed','cancelled') THEN
            attempt_outcome:=CASE w.state COLLATE pg_catalog."C"
                WHEN 'succeeded' THEN 'succeeded' WHEN 'failed' THEN 'failed' WHEN 'cancelled' THEN 'cancelled' END;
            IF pg_catalog.convert_to(a.outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(attempt_outcome,'UTF8') THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid terminal dispatch';
            END IF;
        ELSE
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid retained dispatch';
        END IF;
    ELSIF captured.attempt_present THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected ordinal zero attempt';
    END IF;
    guarded:=w.state COLLATE pg_catalog."C" = 'succeeded'
        AND pg_catalog.convert_to(w.success_origin,'UTF8') = pg_catalog.convert_to('guarded','UTF8');
    guarded:=COALESCE(guarded,FALSE);
    has_resolution:=w.terminal_resolution_operation_id IS NOT NULL;
    IF w.state COLLATE pg_catalog."C" = 'succeeded' THEN
        IF w.result IS NULL OR w.dispatch_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid success result';
        END IF;
        IF NOT guarded AND (pg_catalog.convert_to(w.success_origin,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('reconciled','UTF8')
            OR NOT has_resolution OR w.resolution_operation_id IS DISTINCT FROM w.terminal_resolution_operation_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid success origin';
        END IF;
    ELSE
        IF w.result IS NOT NULL OR w.success_origin IS NOT NULL OR w.resolution_operation_id IS NOT NULL
           OR (has_resolution AND w.state COLLATE pg_catalog."C" NOT IN ('failed','cancelled')) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid terminal resolution shape';
        END IF;
    END IF;
    IF guarded THEN
        IF has_resolution OR w.resolution_operation_id IS NOT NULL OR NOT captured.guard_present
           OR g.guard_id IS DISTINCT FROM w.completion_guard_id OR g.work_id IS DISTINCT FROM w.work_id
           OR g.cycle IS DISTINCT FROM w.cycle OR g.expected_attempt IS DISTINCT FROM w.attempt_count
           OR g.token IS NULL OR g.root_xid IS NULL OR g.root_xid<='0'::pg_catalog.xid8
           OR g.ownership_revision IS NULL OR g.ownership_revision<=0
           OR g.ownership_revision=9223372036854775807::pg_catalog.int8
           OR g.satisfied IS DISTINCT FROM TRUE
           OR pg_catalog.convert_to(g.terminal_state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('succeeded','UTF8')
           OR g.final_fence_at IS NULL OR modkit_events._instant_bytes(g.final_fence_at) IS NULL
           OR w.final_fence_at IS DISTINCT FROM g.final_fence_at OR w.updated_at IS DISTINCT FROM g.final_fence_at
           OR g.result_digest IS DISTINCT FROM pg_catalog.sha256(w.result)
           OR w.completion_result_digest IS DISTINCT FROM g.result_digest
           OR a.evidence IS DISTINCT FROM ''::pg_catalog.bytea
           OR pg_catalog.cardinality(complete_rows) IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid historical completion guard';
        END IF;
        successor:=g.ownership_revision+1;
        h:=complete_rows[1];
        IF w.ownership_revision IS DISTINCT FROM successor OR w.token IS NOT NULL OR w.lease_until IS NOT NULL
           OR h.history_id IS NULL OR h.history_id<=0 OR h.work_id IS DISTINCT FROM w.work_id
           OR h.cycle IS DISTINCT FROM w.cycle OR h.attempt IS DISTINCT FROM w.attempt_count
           OR pg_catalog.convert_to(h.transition,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('complete','UTF8')
           OR pg_catalog.convert_to(h.reason,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('complete','UTF8')
           OR h.token IS NOT NULL OR h.ownership_revision IS DISTINCT FROM successor
           OR h.evidence IS DISTINCT FROM ''::pg_catalog.bytea OR h.recorded_at IS DISTINCT FROM g.final_fence_at THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid historical completion witness';
        END IF;
    ELSE
        IF w.completion_guard_id IS NOT NULL OR w.final_fence_at IS NOT NULL OR w.completion_result_digest IS NOT NULL
           OR captured.guard_present OR pg_catalog.cardinality(complete_rows) IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected completion witness';
        END IF;
    END IF;
    IF has_resolution THEN
        reconciliation_outcome:=CASE w.state COLLATE pg_catalog."C"
            WHEN 'succeeded' THEN 'confirmed_success' WHEN 'failed' THEN 'confirmed_rejection'
            WHEN 'cancelled' THEN 'confirmed_cancelled' END;
        reconciliation_code:=CASE w.state COLLATE pg_catalog."C"
            WHEN 'succeeded' THEN 'reconcile_success' WHEN 'failed' THEN 'reconcile_rejection'
            WHEN 'cancelled' THEN 'reconcile_cancelled' END;
        IF NOT captured.operation_present OR guarded OR w.dispatch_id IS NULL
           OR r.operation_id IS DISTINCT FROM w.terminal_resolution_operation_id
           OR pg_catalog.convert_to(r.operation_kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('reconcile_work','UTF8')
           OR r.work_id IS DISTINCT FROM w.work_id OR r.cycle IS DISTINCT FROM w.cycle
           OR r.attempt IS DISTINCT FROM w.attempt_count OR r.dispatch_id IS DISTINCT FROM w.dispatch_id
           OR pg_catalog.convert_to(r.requested_outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(reconciliation_outcome,'UTF8')
           OR r.expected_revision IS NULL OR r.expected_revision<0 OR r.expected_revision=9223372036854775807::pg_catalog.int8
           OR r.event_id IS NOT NULL OR r.event_digest IS NOT NULL OR r.token IS NOT NULL
           OR r.failed_business_root IS NOT NULL OR r.requested_receipt IS NOT NULL OR r.requested_reason IS NOT NULL
           OR r.retry_at IS NOT NULL OR r.resulting_revision IS NOT NULL
           OR r.resolution_root_xid IS NULL OR r.resolution_root_xid<='0'::pg_catalog.xid8
           OR modkit_events._instant_bytes(r.recorded_at) IS NULL OR r.recorded_at IS DISTINCT FROM w.updated_at
           OR r.evidence IS NULL OR pg_catalog.octet_length(r.evidence)>1048576 OR r.evidence IS DISTINCT FROM a.evidence
           OR r.binding IS NULL OR pg_catalog.octet_length(r.binding)>1048576
           OR pg_catalog.cardinality(reconcile_rows) IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid terminal resolution';
        END IF;
        IF w.state COLLATE pg_catalog."C" = 'succeeded' THEN
            IF r.requested_result IS DISTINCT FROM w.result OR r.result_digest IS DISTINCT FROM pg_catalog.sha256(w.result) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid resolved success result';
            END IF;
        ELSIF r.requested_result IS NOT NULL OR r.result_digest IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected resolution result';
        END IF;
        successor:=r.expected_revision+1;
        h:=reconcile_rows[1];
        IF w.ownership_revision IS DISTINCT FROM successor OR h.history_id IS NULL OR h.history_id<=0
           OR h.work_id IS DISTINCT FROM w.work_id OR h.cycle IS DISTINCT FROM w.cycle OR h.attempt IS DISTINCT FROM w.attempt_count
           OR pg_catalog.convert_to(h.transition,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(reconciliation_code,'UTF8')
           OR pg_catalog.convert_to(h.reason,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(reconciliation_code,'UTF8')
           OR h.token IS NOT NULL OR h.ownership_revision IS DISTINCT FROM successor
           OR h.evidence IS DISTINCT FROM r.evidence OR h.recorded_at IS DISTINCT FROM r.recorded_at THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid reconciliation history witness';
        END IF;
    ELSIF captured.operation_present OR pg_catalog.cardinality(reconcile_rows) IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected terminal resolution';
    END IF;
    -- Literal catalog order, including false/all-NULL suffix for no pointer.
    RETURN QUERY SELECT w.work_id,w.kind,w.subscription_id,w.namespace,w.command_type,w.schema_version_decimal,
        w.runnable_version,w.canonical_version,w.scope_evidence,w.scope_application,w.scope_tenant,w.scope_owner,
        w.idempotency_key,w.intent_evidence,w.semantic_input,w.replay_input,w.protected_binding,w.replay_policy,
        w.max_attempts,w.deadline,w.original_available_at,w.state,w.cancellation_requested,w.token,
        w.ownership_revision,w.lease_until,w.available_at,w.cycle,w.attempt_count,w.dispatch_id,w.result,
        w.created_at,w.updated_at,w.success_origin,w.completion_guard_id,w.final_fence_at,w.completion_result_digest,
        w.resolution_operation_id,w.terminal_resolution_operation_id,has_resolution,
        r.operation_id,r.operation_kind,r.work_id,r.expected_revision,r.cycle,r.attempt,r.dispatch_id,
        r.requested_outcome,r.retry_at,r.requested_result,r.result_digest,r.requested_reason,r.evidence,r.binding,
        r.resolution_root_xid,r.recorded_at;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e15(pg_catalog.uuid) FROM PUBLIC;

-- Segment9: protected subscription and candidate readers, AB-READERS-1.
-- Existing E15 owns hidden work composition; no validation engine is copied.
CREATE FUNCTION modkit_events.e18(p_subscription_id pg_catalog.bytea)
RETURNS TABLE(subscription_id pg_catalog.bytea,manifest pg_catalog.bytea,
    consumer_group pg_catalog.bytea,capacity pg_catalog.int4,
    nonterminal_count pg_catalog.int8,created_at pg_catalog.timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    stored_subscription modkit_events.subscriptions%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_subscription_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid subscription reader arguments';
    END IF;
    SELECT s.* INTO stored_subscription FROM modkit_events.subscriptions AS s
        WHERE s.subscription_id=p_subscription_id;
    IF NOT FOUND THEN RETURN; END IF;
    IF stored_subscription.subscription_id IS DISTINCT FROM p_subscription_id
       OR modkit_events._utf8_valid(stored_subscription.subscription_id,256,TRUE) IS NOT TRUE
       OR stored_subscription.manifest IS NULL OR pg_catalog.octet_length(stored_subscription.manifest)>1048576
       OR modkit_events._utf8_valid(stored_subscription.consumer_group,256,TRUE) IS NOT TRUE
       OR stored_subscription.capacity IS NULL OR stored_subscription.capacity<=0
       OR stored_subscription.nonterminal_count IS NULL OR stored_subscription.nonterminal_count<0
       OR stored_subscription.nonterminal_count>stored_subscription.capacity
       OR modkit_events._instant_bytes(stored_subscription.created_at) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored subscription';
    END IF;
    RETURN QUERY SELECT stored_subscription.subscription_id,stored_subscription.manifest,
        stored_subscription.consumer_group,stored_subscription.capacity,
        stored_subscription.nonterminal_count,stored_subscription.created_at;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e18(pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events.e17(
    p_work_id pg_catalog.uuid,p_kind pg_catalog.text,p_subscription_id pg_catalog.bytea,
    p_namespace pg_catalog.bytea,p_command_type pg_catalog.bytea,
    p_scope_evidence pg_catalog.bytea,p_idempotency_key pg_catalog.bytea
)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    scope_length pg_catalog.int4;
    scope_offset pg_catalog.int4;
    field_length pg_catalog.int4;
    marker pg_catalog.int4;
    field_index pg_catalog.int4;
    scope_fields pg_catalog.bytea[]:=ARRAY[NULL,NULL,NULL]::pg_catalog.bytea[];
    item pg_catalog.record;
    saved_one pg_catalog.record;
    saved_two pg_catalog.record;
    previous_id pg_catalog.uuid;
    checked_count pg_catalog.int4:=0;
    result_index pg_catalog.int4;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_kind IS NULL OR p_scope_evidence IS NULL
       OR (pg_catalog.convert_to(p_kind,'UTF8') IN
           (pg_catalog.convert_to('job','UTF8'),pg_catalog.convert_to('inbox','UTF8'))) IS NOT TRUE
       OR modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE
       OR modkit_events._utf8_valid(p_command_type,256,TRUE) IS NOT TRUE
       OR (p_idempotency_key IS NOT NULL AND modkit_events._utf8_valid(p_idempotency_key,256,TRUE) IS NOT TRUE) THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate reader arguments';
    END IF;
    IF pg_catalog.convert_to(p_kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
        IF p_subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate subscription shape';
        END IF;
    ELSIF modkit_events._utf8_valid(p_subscription_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate subscription shape';
    END IF;
    -- Unpack only: existing _scope_valid remains the normative validator.
    -- Reject helper NULL before arithmetic and check remaining bytes before slices.
    scope_length:=pg_catalog.octet_length(p_scope_evidence);
    IF scope_length<10 OR scope_length>781
       OR pg_catalog.substr(p_scope_evidence,1,5) IS DISTINCT FROM pg_catalog.decode('4d4b534301','hex') THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_offset:=5;
    field_length:=modkit_events._bounded_uint(p_scope_evidence,scope_offset,2,256);
    IF field_length IS NULL OR field_length<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_offset:=scope_offset+2;
    IF field_length>scope_length-scope_offset THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_fields[1]:=pg_catalog.substr(p_scope_evidence,scope_offset+1,field_length);
    scope_offset:=scope_offset+field_length;
    FOR field_index IN 2..3 LOOP
        IF scope_offset>=scope_length THEN
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
        END IF;
        marker:=pg_catalog.get_byte(p_scope_evidence,scope_offset);
        scope_offset:=scope_offset+1;
        IF marker=0 THEN
            scope_fields[field_index]:=NULL;
        ELSIF marker=1 THEN
            field_length:=modkit_events._bounded_uint(p_scope_evidence,scope_offset,2,256);
            IF field_length IS NULL OR field_length<=0 THEN
                RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
            END IF;
            scope_offset:=scope_offset+2;
            IF field_length>scope_length-scope_offset THEN
                RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
            END IF;
            scope_fields[field_index]:=pg_catalog.substr(p_scope_evidence,scope_offset+1,field_length);
            scope_offset:=scope_offset+field_length;
        ELSE
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
        END IF;
    END LOOP;
    IF scope_offset<>scope_length
       OR modkit_events._scope_valid(p_scope_evidence,scope_fields[1],scope_fields[2],scope_fields[3]) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    -- Phase1: one calling-query snapshot. Materialize candidate paths before
    -- invoking E15 once for each distinct ID. An absent direct anchor still
    -- reaches E15 so an attached orphan cannot be hidden by the work lookup.
    FOR item IN
        WITH key_ids AS MATERIALIZED (
            SELECT stored.work_id FROM modkit_events.work AS stored
             WHERE p_idempotency_key IS NOT NULL
               AND stored.kind COLLATE pg_catalog."C" = p_kind COLLATE pg_catalog."C"
               AND stored.namespace=p_namespace AND stored.command_type=p_command_type
               AND pg_catalog.sha256(stored.subscription_id) IS NOT DISTINCT FROM pg_catalog.sha256(p_subscription_id)
               AND pg_catalog.sha256(stored.scope_evidence)=pg_catalog.sha256(p_scope_evidence)
               AND pg_catalog.sha256(stored.idempotency_key)=pg_catalog.sha256(p_idempotency_key)
        ), candidate_ids AS MATERIALIZED (
            SELECT paths.id,pg_catalog.bool_or(paths.key_path) AS key_path
              FROM (SELECT p_work_id AS id,FALSE AS key_path
                    UNION ALL SELECT hit.work_id,TRUE FROM key_ids AS hit) AS paths
             GROUP BY paths.id
        )
        SELECT candidates.id AS selected_id,candidates.key_path,
               (SELECT pg_catalog.count(*) FROM key_ids) AS selected_key_count,
               checked.work_id IS NOT NULL AS checked_present,checked.*
          FROM candidate_ids AS candidates
          LEFT JOIN LATERAL modkit_events.e15(candidates.id) AS checked ON TRUE
         ORDER BY candidates.id
    LOOP
        IF item.selected_id IS NULL OR item.key_path IS NULL OR item.selected_key_count IS NULL
           OR item.selected_key_count<0 OR item.selected_key_count>1
           OR (previous_id IS NOT NULL AND item.selected_id<=previous_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid candidate set cardinality';
        END IF;
        previous_id:=item.selected_id;
        IF NOT item.checked_present THEN
            IF item.key_path OR item.selected_id IS DISTINCT FROM p_work_id THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing selected candidate';
            END IF;
            CONTINUE;
        END IF;
        IF item.work_id IS DISTINCT FROM item.selected_id THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='candidate identity mismatch';
        END IF;
        IF item.key_path THEN
            IF pg_catalog.convert_to(item.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(p_kind,'UTF8')
               OR item.namespace IS DISTINCT FROM p_namespace OR item.command_type IS DISTINCT FROM p_command_type
               OR pg_catalog.sha256(item.subscription_id) IS DISTINCT FROM pg_catalog.sha256(p_subscription_id)
               OR pg_catalog.sha256(item.scope_evidence) IS DISTINCT FROM pg_catalog.sha256(p_scope_evidence)
               OR pg_catalog.sha256(item.idempotency_key) IS DISTINCT FROM pg_catalog.sha256(p_idempotency_key) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='candidate path mismatch';
            END IF;
        END IF;
        checked_count:=checked_count+1;
        IF checked_count=1 THEN saved_one:=item;
        ELSIF checked_count=2 THEN saved_two:=item;
        ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid candidate set cardinality';
        END IF;
    END LOOP;
    -- Phase2 only after ALL E15 observations and sentinels passed. A direct
    -- path remains eligible even if an overlapping digest key path disagrees.
    FOR result_index IN 1..checked_count LOOP
        IF result_index=1 THEN item:=saved_one; ELSE item:=saved_two; END IF;
        IF item.work_id IS DISTINCT FROM p_work_id
           AND item.subscription_id IS DISTINCT FROM p_subscription_id THEN
            RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='candidate subscription identity conflict';
        END IF;
    END LOOP;
    -- Phase3: project only complete saved records, UUID order, literal56 ABI.
    -- No relation read or repeated E15 call occurs in either later phase.
    FOR result_index IN 1..checked_count LOOP
        IF result_index=1 THEN item:=saved_one; ELSE item:=saved_two; END IF;
        RETURN QUERY SELECT item.work_id,item.kind,item.subscription_id,item.namespace,item.command_type,item.schema_version_decimal,
            item.runnable_version,item.canonical_version,item.scope_evidence,item.scope_application,item.scope_tenant,item.scope_owner,
            item.idempotency_key,item.intent_evidence,item.semantic_input,item.replay_input,item.protected_binding,item.replay_policy,
            item.max_attempts,item.deadline,item.original_available_at,item.state,item.cancellation_requested,item.token,
            item.ownership_revision,item.lease_until,item.available_at,item.cycle,item.attempt_count,item.dispatch_id,item.result,
            item.created_at,item.updated_at,item.success_origin,item.completion_guard_id,item.final_fence_at,item.completion_result_digest,
            item.resolution_operation_id,item.terminal_resolution_operation_id,item.resolution_present,
            item.resolution_record_operation_id,item.resolution_record_operation_kind,item.resolution_record_work_id,
            item.resolution_record_expected_revision,item.resolution_record_cycle,item.resolution_record_attempt,
            item.resolution_record_dispatch_id,item.resolution_record_outcome,item.resolution_record_retry_at,
            item.resolution_record_result,item.resolution_record_result_digest,item.resolution_record_reason,
            item.resolution_record_evidence,item.resolution_record_binding,item.resolution_record_resolution_root_xid,
            item.resolution_record_recorded_at;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e17(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

-- Segment10: protected event and combined candidates, AB-SQL v2.
-- E15 remains the single hidden work-composition validator.
CREATE FUNCTION modkit_events.e16(p_subscription_id pg_catalog.bytea,p_event_id pg_catalog.bytea)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz,
    inbox_subscription_id pg_catalog.bytea, original_event_id pg_catalog.bytea,
    envelope_evidence pg_catalog.bytea, original_replay_input pg_catalog.bytea
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE item pg_catalog.record; saved pg_catalog.record; checked_count pg_catalog.int4:=0;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_subscription_id,256,TRUE) IS NOT TRUE
       OR modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid inbox reader arguments';
    END IF;
    -- The indexed digest hit is retained even when full event bytes differ.
    FOR item IN
        WITH inbox_hits AS MATERIALIZED (
            SELECT hit.* FROM modkit_events.inbox AS hit
             WHERE hit.subscription_id=p_subscription_id AND hit.event_digest=pg_catalog.sha256(p_event_id)
        )
        SELECT hit.work_id AS selected_id,hit.work_id AS half_work_id,
               hit.subscription_id AS half_subscription,hit.event_id AS half_event,
               hit.event_digest AS half_digest,hit.envelope_evidence AS half_envelope,hit.replay_input AS half_replay,
               (SELECT pg_catalog.count(*) FROM inbox_hits) AS hit_count,
               checked.work_id IS NOT NULL AS checked_present,checked.*
          FROM inbox_hits AS hit
          LEFT JOIN LATERAL modkit_events.e15(hit.work_id) AS checked ON TRUE
         ORDER BY hit.work_id
    LOOP
        checked_count:=checked_count+1;
        IF item.hit_count IS DISTINCT FROM 1 OR checked_count>1 OR item.selected_id IS NULL
           OR item.checked_present IS DISTINCT FROM TRUE OR item.work_id IS DISTINCT FROM item.selected_id
           OR item.half_work_id IS DISTINCT FROM item.selected_id
           OR pg_catalog.convert_to(item.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('inbox','UTF8')
           OR item.half_subscription IS DISTINCT FROM p_subscription_id
           OR item.subscription_id IS DISTINCT FROM item.half_subscription
           OR item.half_event IS NULL OR item.half_envelope IS NULL OR item.half_replay IS NULL
           OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(p_event_id)
           OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(item.half_event)
           OR item.semantic_input IS DISTINCT FROM item.half_envelope
           OR item.replay_input IS DISTINCT FROM item.half_replay THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid selected inbox composition';
        END IF;
        saved:=item;
    END LOOP;
    IF checked_count=0 THEN RETURN; END IF;
    -- Integrity precedes representability. Do not filter a coherent collision.
    item:=saved;
    IF item.half_event IS DISTINCT FROM p_event_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='inbox event identity conflict';
    END IF;
    RETURN QUERY SELECT item.work_id,item.kind,item.subscription_id,item.namespace,item.command_type,item.schema_version_decimal,
            item.runnable_version,item.canonical_version,item.scope_evidence,item.scope_application,item.scope_tenant,item.scope_owner,
            item.idempotency_key,item.intent_evidence,item.semantic_input,item.replay_input,item.protected_binding,item.replay_policy,
            item.max_attempts,item.deadline,item.original_available_at,item.state,item.cancellation_requested,item.token,
            item.ownership_revision,item.lease_until,item.available_at,item.cycle,item.attempt_count,item.dispatch_id,item.result,
            item.created_at,item.updated_at,item.success_origin,item.completion_guard_id,item.final_fence_at,item.completion_result_digest,
            item.resolution_operation_id,item.terminal_resolution_operation_id,item.resolution_present,
            item.resolution_record_operation_id,item.resolution_record_operation_kind,item.resolution_record_work_id,
            item.resolution_record_expected_revision,item.resolution_record_cycle,item.resolution_record_attempt,
            item.resolution_record_dispatch_id,item.resolution_record_outcome,item.resolution_record_retry_at,
            item.resolution_record_result,item.resolution_record_result_digest,item.resolution_record_reason,
            item.resolution_record_evidence,item.resolution_record_binding,item.resolution_record_resolution_root_xid,
            item.resolution_record_recorded_at,
        item.half_subscription,item.half_event,item.half_envelope,item.half_replay;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e16(pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

CREATE FUNCTION modkit_events.e34(
    p_work_id pg_catalog.uuid,p_kind pg_catalog.text,p_subscription_id pg_catalog.bytea,
    p_namespace pg_catalog.bytea,p_command_type pg_catalog.bytea,
    p_scope_evidence pg_catalog.bytea,p_idempotency_key pg_catalog.bytea,p_original_event_id pg_catalog.bytea
)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz,
    inbox_half_present pg_catalog.bool,
    inbox_subscription_id pg_catalog.bytea, original_event_id pg_catalog.bytea,
    envelope_evidence pg_catalog.bytea, original_replay_input pg_catalog.bytea
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    scope_length pg_catalog.int4; scope_offset pg_catalog.int4; field_length pg_catalog.int4;
    marker pg_catalog.int4; field_index pg_catalog.int4;
    scope_fields pg_catalog.bytea[]:=ARRAY[NULL,NULL,NULL]::pg_catalog.bytea[];
    raw_key_ids pg_catalog.uuid[]; raw_event_rows modkit_events.inbox[];
    raw_direct_present pg_catalog.bool; raw_key_count pg_catalog.int4; raw_event_count pg_catalog.int4;
    event_hit modkit_events.inbox%ROWTYPE;
    event_only pg_catalog.bool:=FALSE;
    direct_seen pg_catalog.bool:=FALSE; key_seen pg_catalog.bool:=FALSE; event_seen pg_catalog.bool:=FALSE;
    item pg_catalog.record; saved_one pg_catalog.record; saved_two pg_catalog.record; saved_three pg_catalog.record;
    swap_record pg_catalog.record; previous_key_id pg_catalog.uuid;
    total_count pg_catalog.int4:=0; key_count pg_catalog.int4:=0; event_checked_count pg_catalog.int4:=0;
    result_index pg_catalog.int4;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_kind IS NULL OR p_scope_evidence IS NULL
       OR (pg_catalog.convert_to(p_kind,'UTF8') IN
           (pg_catalog.convert_to('job','UTF8'),pg_catalog.convert_to('inbox','UTF8'))) IS NOT TRUE
       OR modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE
       OR modkit_events._utf8_valid(p_command_type,256,TRUE) IS NOT TRUE
       OR (p_idempotency_key IS NOT NULL AND modkit_events._utf8_valid(p_idempotency_key,256,TRUE) IS NOT TRUE) THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate reader arguments';
    END IF;
    IF pg_catalog.convert_to(p_kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
        IF p_subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate subscription shape';
        END IF;
    ELSIF modkit_events._utf8_valid(p_subscription_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate subscription shape';
    END IF;
    IF pg_catalog.convert_to(p_kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('inbox','UTF8')
       OR modkit_events._utf8_valid(p_original_event_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid combined reader arguments';
    END IF;
    -- Unpack only: existing _scope_valid remains the normative validator.
    -- Reject helper NULL before arithmetic and check remaining bytes before slices.
    scope_length:=pg_catalog.octet_length(p_scope_evidence);
    IF scope_length<10 OR scope_length>781
       OR pg_catalog.substr(p_scope_evidence,1,5) IS DISTINCT FROM pg_catalog.decode('4d4b534301','hex') THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_offset:=5;
    field_length:=modkit_events._bounded_uint(p_scope_evidence,scope_offset,2,256);
    IF field_length IS NULL OR field_length<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_offset:=scope_offset+2;
    IF field_length>scope_length-scope_offset THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    scope_fields[1]:=pg_catalog.substr(p_scope_evidence,scope_offset+1,field_length);
    scope_offset:=scope_offset+field_length;
    FOR field_index IN 2..3 LOOP
        IF scope_offset>=scope_length THEN
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
        END IF;
        marker:=pg_catalog.get_byte(p_scope_evidence,scope_offset);
        scope_offset:=scope_offset+1;
        IF marker=0 THEN
            scope_fields[field_index]:=NULL;
        ELSIF marker=1 THEN
            field_length:=modkit_events._bounded_uint(p_scope_evidence,scope_offset,2,256);
            IF field_length IS NULL OR field_length<=0 THEN
                RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
            END IF;
            scope_offset:=scope_offset+2;
            IF field_length>scope_length-scope_offset THEN
                RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
            END IF;
            scope_fields[field_index]:=pg_catalog.substr(p_scope_evidence,scope_offset+1,field_length);
            scope_offset:=scope_offset+field_length;
        ELSE
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
        END IF;
    END LOOP;
    IF scope_offset<>scope_length
       OR modkit_events._scope_valid(p_scope_evidence,scope_fields[1],scope_fields[2],scope_fields[3]) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid candidate scope';
    END IF;
    -- Phase1: raw bounded discovery only, using exactly E17's key predicate.
    -- The direct singleton is retained separately even when work is absent.
    SELECT ARRAY(SELECT stored.work_id FROM modkit_events.work AS stored
                 WHERE p_idempotency_key IS NOT NULL
               AND stored.kind COLLATE pg_catalog."C" = p_kind COLLATE pg_catalog."C"
               AND stored.namespace=p_namespace AND stored.command_type=p_command_type
               AND pg_catalog.sha256(stored.subscription_id) IS NOT DISTINCT FROM pg_catalog.sha256(p_subscription_id)
               AND pg_catalog.sha256(stored.scope_evidence)=pg_catalog.sha256(p_scope_evidence)
               AND pg_catalog.sha256(stored.idempotency_key)=pg_catalog.sha256(p_idempotency_key)
                 ORDER BY stored.work_id),
           ARRAY(SELECT hit FROM modkit_events.inbox AS hit
                 WHERE hit.subscription_id=p_subscription_id
                   AND hit.event_digest=pg_catalog.sha256(p_original_event_id)
                 ORDER BY hit.work_id),
           EXISTS(SELECT 1 FROM modkit_events.work AS direct_work WHERE direct_work.work_id=p_work_id)
      INTO raw_key_ids,raw_event_rows,raw_direct_present;
    raw_key_count:=pg_catalog.cardinality(raw_key_ids); raw_event_count:=pg_catalog.cardinality(raw_event_rows);
    IF raw_key_count IS NULL OR raw_key_count<0 OR raw_key_count>1
       OR raw_event_count IS NULL OR raw_event_count<0 OR raw_event_count>1
       OR raw_direct_present IS NULL OR (raw_key_count=1 AND raw_key_ids[1] IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined discovery cardinality';
    END IF;
    IF raw_event_count=1 THEN
        event_hit:=raw_event_rows[1];
        IF event_hit.work_id IS NULL OR event_hit.subscription_id IS DISTINCT FROM p_subscription_id
           OR event_hit.event_id IS NULL OR event_hit.envelope_evidence IS NULL OR event_hit.replay_input IS NULL
           OR event_hit.event_digest IS DISTINCT FROM pg_catalog.sha256(p_original_event_id)
           OR event_hit.event_digest IS DISTINCT FROM pg_catalog.sha256(event_hit.event_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined event discovery';
        END IF;
        event_only:=event_hit.work_id<>p_work_id AND pg_catalog.array_position(raw_key_ids,event_hit.work_id) IS NULL;
    END IF;
    -- Phase2 MUST complete before E17 can classify a subscription collision.
    -- An event-only LEFT E15 row retains selected ID even on missing checked data.
    IF event_only THEN
        FOR item IN
            WITH event_checked AS MATERIALIZED (
                SELECT event_hit.work_id AS selected_id,FALSE AS direct_path,FALSE AS key_path,TRUE AS event_path,
                       checked.work_id IS NOT NULL AS checked_present,
                       event_hit.work_id IS NOT NULL AS half_present,event_hit.work_id AS half_work_id,
                       event_hit.subscription_id AS half_subscription,event_hit.event_id AS half_event,
                       event_hit.event_digest AS half_digest,event_hit.envelope_evidence AS half_envelope,
                       event_hit.replay_input AS half_replay,checked.*
                  FROM (VALUES(event_hit.work_id)) AS selected(id)
                  LEFT JOIN LATERAL modkit_events.e15(selected.id) AS checked ON TRUE
            )
            SELECT (SELECT pg_catalog.count(*) FROM event_checked) AS captured_count,tagged.*
              FROM event_checked AS tagged
        LOOP
            event_checked_count:=event_checked_count+1;
            IF item.captured_count IS DISTINCT FROM 1 OR event_checked_count>1 THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined event cardinality';
            END IF;
            IF item.selected_id IS NULL OR item.checked_present IS DISTINCT FROM TRUE
               OR item.work_id IS DISTINCT FROM item.selected_id
               OR item.direct_path IS NULL OR item.key_path IS NULL OR item.event_path IS NULL
               OR (item.direct_path OR item.key_path OR item.event_path) IS NOT TRUE
               OR item.direct_path IS DISTINCT FROM (item.selected_id=p_work_id)
               OR item.key_path IS DISTINCT FROM (item.selected_id=ANY(raw_key_ids))
               OR item.event_path IS DISTINCT FROM (raw_event_count=1 AND item.selected_id=event_hit.work_id) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined candidate identity';
            END IF;
            IF pg_catalog.convert_to(item.kind,'UTF8') = pg_catalog.convert_to('inbox','UTF8') THEN
                IF item.half_present IS DISTINCT FROM TRUE OR item.half_work_id IS DISTINCT FROM item.selected_id
                   OR item.half_subscription IS NULL OR item.half_event IS NULL
                   OR item.half_envelope IS NULL OR item.half_replay IS NULL
                   OR item.subscription_id IS DISTINCT FROM item.half_subscription
                   OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(item.half_event)
                   OR item.semantic_input IS DISTINCT FROM item.half_envelope
                   OR item.replay_input IS DISTINCT FROM item.half_replay THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined inbox projection';
                END IF;
            ELSIF pg_catalog.convert_to(item.kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
                IF item.direct_path IS DISTINCT FROM TRUE OR item.half_present IS DISTINCT FROM FALSE
                   OR item.half_work_id IS NOT NULL OR item.half_subscription IS NOT NULL
                   OR item.half_event IS NOT NULL OR item.half_digest IS NOT NULL
                   OR item.half_envelope IS NOT NULL OR item.half_replay IS NOT NULL THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined job projection';
                END IF;
            ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined candidate kind';
            END IF;
            IF item.event_path THEN
                IF item.half_present IS DISTINCT FROM TRUE OR item.half_subscription IS DISTINCT FROM p_subscription_id
                   OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(p_original_event_id) THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined event path';
                END IF;
            END IF;
            saved_one:=item; total_count:=1; event_seen:=TRUE;
        END LOOP;
        IF event_checked_count<>1 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing combined event candidate';
        END IF;
    END IF;
    -- Phase3: one fully consumed/materialized E17 invocation. Every overlapping
    -- event ID was a raw direct/key ID and reaches E15 inside E17 before PZ002.
    -- Reuse these checked56 fields, never repeat E15 for event overlap.
    FOR item IN
        WITH key_checked AS MATERIALIZED (
            SELECT checked.* FROM modkit_events.e17(p_work_id,p_kind,p_subscription_id,p_namespace,
                p_command_type,p_scope_evidence,p_idempotency_key) AS checked
        )
        SELECT (SELECT pg_catalog.count(*) FROM key_checked) AS captured_count,
               checked.work_id AS selected_id,(checked.work_id=p_work_id) AS direct_path,
               (checked.work_id=ANY(raw_key_ids)) AS key_path,
               (raw_event_count=1 AND checked.work_id=event_hit.work_id) AS event_path,
               checked.work_id IS NOT NULL AS checked_present,
               half.work_id IS NOT NULL AS half_present,half.work_id AS half_work_id,
               half.subscription_id AS half_subscription,half.event_id AS half_event,
               half.event_digest AS half_digest,half.envelope_evidence AS half_envelope,half.replay_input AS half_replay,
               checked.*
          FROM key_checked AS checked
          LEFT JOIN modkit_events.inbox AS half ON half.work_id=checked.work_id
         ORDER BY checked.work_id
    LOOP
        key_count:=key_count+1;
        IF item.captured_count IS NULL OR item.captured_count<1 OR item.captured_count>2
           OR key_count>2 OR (previous_key_id IS NOT NULL AND item.selected_id<=previous_key_id)
           OR (item.direct_path OR item.key_path) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined key cardinality';
        END IF;
        previous_key_id:=item.selected_id;
        IF item.selected_id IS NULL OR item.checked_present IS DISTINCT FROM TRUE
           OR item.work_id IS DISTINCT FROM item.selected_id
           OR item.direct_path IS NULL OR item.key_path IS NULL OR item.event_path IS NULL
           OR (item.direct_path OR item.key_path OR item.event_path) IS NOT TRUE
           OR item.direct_path IS DISTINCT FROM (item.selected_id=p_work_id)
           OR item.key_path IS DISTINCT FROM (item.selected_id=ANY(raw_key_ids))
           OR item.event_path IS DISTINCT FROM (raw_event_count=1 AND item.selected_id=event_hit.work_id) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined candidate identity';
        END IF;
        IF pg_catalog.convert_to(item.kind,'UTF8') = pg_catalog.convert_to('inbox','UTF8') THEN
            IF item.half_present IS DISTINCT FROM TRUE OR item.half_work_id IS DISTINCT FROM item.selected_id
               OR item.half_subscription IS NULL OR item.half_event IS NULL
               OR item.half_envelope IS NULL OR item.half_replay IS NULL
               OR item.subscription_id IS DISTINCT FROM item.half_subscription
               OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(item.half_event)
               OR item.semantic_input IS DISTINCT FROM item.half_envelope
               OR item.replay_input IS DISTINCT FROM item.half_replay THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined inbox projection';
            END IF;
        ELSIF pg_catalog.convert_to(item.kind,'UTF8') = pg_catalog.convert_to('job','UTF8') THEN
            IF item.direct_path IS DISTINCT FROM TRUE OR item.half_present IS DISTINCT FROM FALSE
               OR item.half_work_id IS NOT NULL OR item.half_subscription IS NOT NULL
               OR item.half_event IS NOT NULL OR item.half_digest IS NOT NULL
               OR item.half_envelope IS NOT NULL OR item.half_replay IS NOT NULL THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined job projection';
            END IF;
        ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined candidate kind';
        END IF;
        IF item.event_path THEN
            IF item.half_present IS DISTINCT FROM TRUE OR item.half_subscription IS DISTINCT FROM p_subscription_id
               OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(p_original_event_id) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined event path';
            END IF;
        END IF;
        -- Separate guards avoid referencing any unassigned RECORD local.
        IF total_count>=1 THEN
            IF saved_one.selected_id=item.selected_id THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='duplicate combined candidate';
            END IF;
        END IF;
        IF total_count>=2 THEN
            IF saved_two.selected_id=item.selected_id THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='duplicate combined candidate';
            END IF;
        END IF;
        total_count:=total_count+1;
        IF total_count=1 THEN saved_one:=item;
        ELSIF total_count=2 THEN saved_two:=item;
        ELSIF total_count=3 THEN saved_three:=item;
        ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid combined family cardinality';
        END IF;
        IF item.direct_path THEN direct_seen:=TRUE; END IF;
        IF item.key_path THEN key_seen:=TRUE; END IF;
        IF item.event_path THEN event_seen:=TRUE; END IF;
    END LOOP;
    IF raw_direct_present IS DISTINCT FROM direct_seen
       OR (raw_key_count=1) IS DISTINCT FROM key_seen
       OR (raw_event_count=1) IS DISTINCT FROM event_seen THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing combined discovery member';
    END IF;
    -- Full family is validated before output. Sort at most3 saved local records;
    -- a coherent event-hash conflict remains full evidence, unlike E16.
    IF total_count>=2 THEN
        IF saved_one.selected_id>saved_two.selected_id THEN
            swap_record:=saved_one; saved_one:=saved_two; saved_two:=swap_record;
        END IF;
    END IF;
    IF total_count=3 THEN
        IF saved_two.selected_id>saved_three.selected_id THEN
            swap_record:=saved_two; saved_two:=saved_three; saved_three:=swap_record;
        END IF;
        IF saved_one.selected_id>saved_two.selected_id THEN
            swap_record:=saved_one; saved_one:=saved_two; saved_two:=swap_record;
        END IF;
    END IF;
    FOR result_index IN 1..total_count LOOP
        IF result_index=1 THEN item:=saved_one;
        ELSIF result_index=2 THEN item:=saved_two;
        ELSE item:=saved_three;
        END IF;
        RETURN QUERY SELECT item.work_id,item.kind,item.subscription_id,item.namespace,item.command_type,item.schema_version_decimal,
            item.runnable_version,item.canonical_version,item.scope_evidence,item.scope_application,item.scope_tenant,item.scope_owner,
            item.idempotency_key,item.intent_evidence,item.semantic_input,item.replay_input,item.protected_binding,item.replay_policy,
            item.max_attempts,item.deadline,item.original_available_at,item.state,item.cancellation_requested,item.token,
            item.ownership_revision,item.lease_until,item.available_at,item.cycle,item.attempt_count,item.dispatch_id,item.result,
            item.created_at,item.updated_at,item.success_origin,item.completion_guard_id,item.final_fence_at,item.completion_result_digest,
            item.resolution_operation_id,item.terminal_resolution_operation_id,item.resolution_present,
            item.resolution_record_operation_id,item.resolution_record_operation_kind,item.resolution_record_work_id,
            item.resolution_record_expected_revision,item.resolution_record_cycle,item.resolution_record_attempt,
            item.resolution_record_dispatch_id,item.resolution_record_outcome,item.resolution_record_retry_at,
            item.resolution_record_result,item.resolution_record_result_digest,item.resolution_record_reason,
            item.resolution_record_evidence,item.resolution_record_binding,item.resolution_record_resolution_root_xid,
            item.resolution_record_recorded_at,
            item.half_present,item.half_subscription,item.half_event,item.half_envelope,item.half_replay;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e34(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

-- Segment11: immutable subscription registration, selected AB-SQL v2.
CREATE FUNCTION modkit_events.e01(
    p_subscription_id pg_catalog.bytea,p_manifest pg_catalog.bytea,
    p_consumer_group pg_catalog.bytea,p_capacity pg_catalog.int4
)
RETURNS TABLE(ok pg_catalog.bool)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE captured modkit_events.subscriptions%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_subscription_id,256,TRUE) IS NOT TRUE
       OR p_manifest IS NULL OR pg_catalog.octet_length(p_manifest)>1048576
       OR modkit_events._utf8_valid(p_consumer_group,256,TRUE) IS NOT TRUE
       OR p_capacity IS NULL OR p_capacity<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid registration arguments';
    END IF;
    -- Count starts at0 only for a new parent. Conflict never updates a winner.
    -- Creation time may precede a uniqueness wait; it is not a final fence.
    INSERT INTO modkit_events.subscriptions AS registration
        (subscription_id,manifest,consumer_group,capacity,nonterminal_count,created_at)
        VALUES(p_subscription_id,p_manifest,p_consumer_group,p_capacity,0,pg_catalog.clock_timestamp())
        ON CONFLICT(subscription_id) DO NOTHING;
    -- Parent mutex precedes any future work acquisition. A separate VOLATILE
    -- READ COMMITTED command captures the winner after any uniqueness/lock wait.
    PERFORM stored.subscription_id FROM modkit_events.subscriptions AS stored
        WHERE stored.subscription_id=p_subscription_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing registration parent';
    END IF;
    SELECT stored.* INTO captured FROM modkit_events.subscriptions AS stored
        WHERE stored.subscription_id=p_subscription_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing registration parent';
    END IF;
    -- Validate stored integrity before comparing immutable caller evidence.
    IF captured.subscription_id IS DISTINCT FROM p_subscription_id
       OR modkit_events._utf8_valid(captured.subscription_id,256,TRUE) IS NOT TRUE
       OR captured.manifest IS NULL OR pg_catalog.octet_length(captured.manifest)>1048576
       OR modkit_events._utf8_valid(captured.consumer_group,256,TRUE) IS NOT TRUE
       OR captured.capacity IS NULL OR captured.capacity<=0
       OR captured.nonterminal_count IS NULL OR captured.nonterminal_count<0
       OR captured.nonterminal_count>captured.capacity
       OR modkit_events._instant_bytes(captured.created_at) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored registration';
    END IF;
    IF captured.manifest IS DISTINCT FROM p_manifest
       OR captured.consumer_group IS DISTINCT FROM p_consumer_group
       OR captured.capacity IS DISTINCT FROM p_capacity THEN
        RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='registration identity conflict';
    END IF;
    -- An exact repeat preserves its current count and original created_at.
    RETURN QUERY SELECT TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e01(pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;


-- Segment12: selected bounded E03-only admission. Still NOT_READY.
-- Cooperative writers lock full parent before work, create both halves atomically,
-- retain immutable identities/keys and never delete admitted identities/halves.
-- Caller lock history is caller-owned. Foreign aliases are observations only.
CREATE FUNCTION modkit_events.e03(
    p_work_id pg_catalog.uuid,p_kind pg_catalog.text,p_subscription_id pg_catalog.bytea,
    p_namespace pg_catalog.bytea,p_command_type pg_catalog.bytea,
    p_scope_evidence pg_catalog.bytea,p_idempotency_key pg_catalog.bytea,
    p_canonical_version pg_catalog.int4,p_schema_version_decimal pg_catalog.bytea,
    p_scope_application pg_catalog.bytea,p_scope_tenant pg_catalog.bytea,p_scope_owner pg_catalog.bytea,
    p_intent_evidence pg_catalog.bytea,p_semantic_input pg_catalog.bytea,p_replay_input pg_catalog.bytea,
    p_protected_binding pg_catalog.bytea,p_replay_policy pg_catalog.text,p_max_attempts pg_catalog.int4,
    p_deadline pg_catalog.timestamptz,p_original_available_at pg_catalog.timestamptz,
    p_event_id pg_catalog.bytea,p_event_canonical_version pg_catalog.int4,
    p_envelope_evidence pg_catalog.bytea,p_event_replay_input pg_catalog.bytea,
    p_supported pg_catalog.bool,p_broker_reference pg_catalog.bytea,p_transport_observation pg_catalog.bytea
)
RETURNS TABLE(work_id pg_catalog.uuid,inserted pg_catalog.bool)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    parent_row modkit_events.subscriptions%ROWTYPE;
    envelope pg_catalog.bytea; event_fields pg_catalog.bytea[];
    own_ids pg_catalog.uuid[]; final_own_ids pg_catalog.uuid[];
    lock_id pg_catalog.uuid; previous_id pg_catalog.uuid;
    key_count pg_catalog.int8; event_count pg_catalog.int8;
    capture_pass pg_catalog.int4; selected_count pg_catalog.int4; present_count pg_catalog.int4;
    item pg_catalog.record; saved_one pg_catalog.record; saved_two pg_catalog.record; saved_three pg_catalog.record;
    direct_seen pg_catalog.int4; key_seen pg_catalog.int4; event_seen pg_catalog.int4;
    affected pg_catalog.int8; generated_id pg_catalog.int8;
    creation_time pg_catalog.timestamptz; intake_time pg_catalog.timestamptz; delivery_time pg_catalog.timestamptz;
    runnable pg_catalog.int4:=NULL; initial_state pg_catalog.text; intake_code pg_catalog.text;
BEGIN
    -- P0: complete byte/native input validation before any relation access.
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL
       OR pg_catalog.convert_to(p_kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('inbox','UTF8')
       OR (pg_catalog.convert_to(p_replay_policy,'UTF8') IN
           (pg_catalog.convert_to('disabled','UTF8'),pg_catalog.convert_to('application_safe','UTF8'))) IS NOT TRUE
       OR modkit_events._intent_valid(p_kind,p_subscription_id,p_namespace,p_command_type,
           p_scope_evidence,p_idempotency_key,p_canonical_version,p_schema_version_decimal,
           p_scope_application,p_scope_tenant,p_scope_owner,p_intent_evidence,p_semantic_input,p_replay_input,
           p_protected_binding,p_replay_policy,p_max_attempts,p_deadline,p_original_available_at) IS NOT TRUE
       OR modkit_events._protected_frame_valid(p_protected_binding) IS NOT TRUE
       OR modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE
       OR p_event_canonical_version IS DISTINCT FROM 1
       OR p_envelope_evidence IS NULL OR pg_catalog.octet_length(p_envelope_evidence)>1048576
       OR p_event_replay_input IS NULL OR pg_catalog.octet_length(p_event_replay_input)>1048576
       OR p_supported IS NULL OR p_broker_reference IS NULL OR p_transport_observation IS NULL
       OR pg_catalog.octet_length(p_broker_reference)>1048576
       OR pg_catalog.octet_length(p_transport_observation)>1048576 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid inbox admission arguments';
    END IF;
    envelope:=modkit_events._event_replay_frame(p_event_replay_input);
    IF envelope IS NULL OR envelope IS DISTINCT FROM p_envelope_evidence
       OR envelope IS DISTINCT FROM p_semantic_input OR p_event_replay_input IS DISTINCT FROM p_replay_input THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid inbox event input';
    END IF;
    event_fields:=modkit_events._record_fields(envelope,pg_catalog.convert_to('event-envelope','UTF8'),5);
    IF event_fields IS NULL OR event_fields[1] IS DISTINCT FROM p_event_id
       OR event_fields[2] IS DISTINCT FROM p_command_type
       OR event_fields[3] IS DISTINCT FROM p_schema_version_decimal THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid inbox event identity';
    END IF;
    -- Decimal validated above. Narrow only a proven positive int4 representation.
    IF p_supported AND (pg_catalog.octet_length(p_schema_version_decimal)<10
       OR (pg_catalog.octet_length(p_schema_version_decimal)=10
           AND p_schema_version_decimal<=pg_catalog.convert_to('2147483647','UTF8'))) THEN
        runnable:=pg_catalog.convert_from(p_schema_version_decimal,'UTF8')::pg_catalog.int4;
    END IF;
    IF runnable IS NULL THEN initial_state:='blocked_schema'; intake_code:='intake_blocked';
    ELSE initial_state:='queued'; intake_code:='intake_runnable'; END IF;

    -- P1: requested FULL parent mutex, then a separate fresh under-lock read.
    PERFORM stored.subscription_id FROM modkit_events.subscriptions AS stored
        WHERE stored.subscription_id=p_subscription_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='subscription not registered'; END IF;
    SELECT stored.* INTO parent_row FROM modkit_events.subscriptions AS stored
        WHERE stored.subscription_id=p_subscription_id;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing locked subscription'; END IF;
    IF parent_row.subscription_id IS DISTINCT FROM p_subscription_id
       OR modkit_events._utf8_valid(parent_row.subscription_id,256,TRUE) IS NOT TRUE
       OR parent_row.manifest IS NULL OR pg_catalog.octet_length(parent_row.manifest)>1048576
       OR modkit_events._utf8_valid(parent_row.consumer_group,256,TRUE) IS NOT TRUE
       OR parent_row.capacity IS NULL OR parent_row.capacity<=0
       OR parent_row.nonterminal_count IS NULL OR parent_row.nonterminal_count<0
       OR parent_row.nonterminal_count>parent_row.capacity
       OR modkit_events._instant_bytes(parent_row.created_at) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid stored subscription';
    END IF;

    -- P2: raw paths before mutation locks. No LIMIT masks corrupt cardinality.
    WITH key_ids AS MATERIALIZED (
        SELECT stored.work_id FROM modkit_events.work AS stored
         WHERE p_idempotency_key IS NOT NULL AND stored.kind COLLATE pg_catalog."C"='inbox' COLLATE pg_catalog."C"
           AND stored.namespace=p_namespace AND stored.command_type=p_command_type
           AND pg_catalog.sha256(stored.subscription_id) IS NOT DISTINCT FROM pg_catalog.sha256(p_subscription_id)
           AND pg_catalog.sha256(stored.scope_evidence)=pg_catalog.sha256(p_scope_evidence)
           AND pg_catalog.sha256(stored.idempotency_key)=pg_catalog.sha256(p_idempotency_key)
    ), event_ids AS MATERIALIZED (
        SELECT half.work_id FROM modkit_events.inbox AS half
         WHERE half.subscription_id=p_subscription_id AND half.event_digest=pg_catalog.sha256(p_event_id)
    ), candidate_ids AS MATERIALIZED (
        SELECT p_work_id AS id UNION SELECT k.work_id FROM key_ids AS k UNION SELECT e.work_id FROM event_ids AS e
    )
    SELECT (SELECT pg_catalog.count(*) FROM key_ids),(SELECT pg_catalog.count(*) FROM event_ids),
           ARRAY(SELECT c.id FROM candidate_ids AS c JOIN modkit_events.work AS actual ON actual.work_id=c.id
                  WHERE actual.kind COLLATE pg_catalog."C"='inbox' COLLATE pg_catalog."C"
                    AND actual.subscription_id=p_subscription_id ORDER BY c.id)
      INTO key_count,event_count,own_ids;
    IF key_count>1 OR event_count>1 OR pg_catalog.cardinality(own_ids)>3 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid preliminary admission family';
    END IF;
    FOREACH lock_id IN ARRAY own_ids LOOP
        PERFORM stored.work_id FROM modkit_events.work AS stored
            WHERE stored.work_id=lock_id AND stored.kind COLLATE pg_catalog."C"='inbox' COLLATE pg_catalog."C"
              AND stored.subscription_id=p_subscription_id FOR NO KEY UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='changed own admission member'; END IF;
    END LOOP;

    -- P3/P6: pass1 is the final fresh snapshot after all own-work waits.
    -- Pass2 exists ONLY after a lost reservation, and is one separate command.
    -- All paths, including absent direct, are materialized before one E15 per ID.
    FOR capture_pass IN 1..2 LOOP
        selected_count:=0; present_count:=0; previous_id:=NULL;
        direct_seen:=0; key_seen:=0; event_seen:=0;
        final_own_ids:=ARRAY[]::pg_catalog.uuid[];
        FOR item IN
            WITH key_ids AS MATERIALIZED (
                SELECT stored.work_id FROM modkit_events.work AS stored
                 WHERE p_idempotency_key IS NOT NULL AND stored.kind COLLATE pg_catalog."C"='inbox' COLLATE pg_catalog."C"
                   AND stored.namespace=p_namespace AND stored.command_type=p_command_type
                   AND pg_catalog.sha256(stored.subscription_id) IS NOT DISTINCT FROM pg_catalog.sha256(p_subscription_id)
                   AND pg_catalog.sha256(stored.scope_evidence)=pg_catalog.sha256(p_scope_evidence)
                   AND pg_catalog.sha256(stored.idempotency_key)=pg_catalog.sha256(p_idempotency_key)
            ), event_ids AS MATERIALIZED (
                SELECT half.work_id FROM modkit_events.inbox AS half
                 WHERE half.subscription_id=p_subscription_id AND half.event_digest=pg_catalog.sha256(p_event_id)
            ), candidate_ids AS MATERIALIZED (
                SELECT paths.id,pg_catalog.bool_or(paths.direct_path) AS direct_path,
                       pg_catalog.bool_or(paths.key_path) AS key_path,pg_catalog.bool_or(paths.event_path) AS event_path
                  FROM (SELECT p_work_id AS id,TRUE AS direct_path,FALSE AS key_path,FALSE AS event_path
                        UNION ALL SELECT k.work_id,FALSE,TRUE,FALSE FROM key_ids AS k
                        UNION ALL SELECT e.work_id,FALSE,FALSE,TRUE FROM event_ids AS e) AS paths
                 GROUP BY paths.id
            ), captured AS MATERIALIZED (
                SELECT c.id AS selected_id,c.direct_path,c.key_path,c.event_path,
                       actual.work_id IS NOT NULL AS raw_present,
                       checked.work_id IS NOT NULL AS checked_present,
                       half.work_id IS NOT NULL AS half_present,half.work_id AS half_work_id,
                       half.subscription_id AS half_subscription,half.event_id AS half_event,
                       half.event_digest AS half_digest,half.envelope_evidence AS half_envelope,
                       half.replay_input AS half_replay,checked.*
                  FROM candidate_ids AS c
                  LEFT JOIN modkit_events.work AS actual ON actual.work_id=c.id
                  LEFT JOIN LATERAL modkit_events.e15(c.id) AS checked ON TRUE
                  LEFT JOIN modkit_events.inbox AS half ON half.work_id=c.id
            )
            SELECT (SELECT pg_catalog.count(*) FROM key_ids) AS raw_key_count,
                   (SELECT pg_catalog.count(*) FROM event_ids) AS raw_event_count,
                   (SELECT pg_catalog.count(*) FROM captured) AS captured_count,captured.*
              FROM captured ORDER BY selected_id
        LOOP
            selected_count:=selected_count+1;
            IF item.captured_count IS NULL OR item.captured_count<1 OR item.captured_count>3
               OR selected_count>3 OR item.raw_key_count IS NULL OR item.raw_key_count<0 OR item.raw_key_count>1
               OR item.raw_event_count IS NULL OR item.raw_event_count<0 OR item.raw_event_count>1
               OR item.selected_id IS NULL OR (previous_id IS NOT NULL AND item.selected_id<=previous_id)
               OR item.direct_path IS DISTINCT FROM (item.selected_id=p_work_id)
               OR item.key_path IS NULL OR item.event_path IS NULL
               OR (item.direct_path OR item.key_path OR item.event_path) IS NOT TRUE
               OR item.raw_present IS DISTINCT FROM item.checked_present THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid captured admission family';
            END IF;
            previous_id:=item.selected_id;
            IF item.direct_path THEN direct_seen:=direct_seen+1; END IF;
            IF item.key_path THEN key_seen:=key_seen+1; END IF;
            IF item.event_path THEN event_seen:=event_seen+1; END IF;
            IF item.checked_present IS DISTINCT FROM TRUE THEN
                -- E15 has still checked absence of BOTH subtypes for this ID.
                IF item.direct_path IS DISTINCT FROM TRUE OR item.key_path OR item.event_path
                   OR item.half_present IS DISTINCT FROM FALSE THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing selected admission member';
                END IF;
                CONTINUE;
            END IF;
            IF item.work_id IS DISTINCT FROM item.selected_id THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='admission candidate identity mismatch';
            END IF;
            IF pg_catalog.convert_to(item.kind,'UTF8')=pg_catalog.convert_to('inbox','UTF8') THEN
                IF item.half_present IS DISTINCT FROM TRUE OR item.half_work_id IS DISTINCT FROM item.selected_id
                   OR item.half_subscription IS NULL OR item.half_event IS NULL
                   OR item.half_envelope IS NULL OR item.half_replay IS NULL
                   OR item.subscription_id IS DISTINCT FROM item.half_subscription
                   OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(item.half_event)
                   OR item.semantic_input IS DISTINCT FROM item.half_envelope
                   OR item.replay_input IS DISTINCT FROM item.half_replay THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission inbox projection';
                END IF;
                IF item.subscription_id=p_subscription_id THEN
                    final_own_ids:=pg_catalog.array_append(final_own_ids,item.selected_id);
                END IF;
            ELSIF pg_catalog.convert_to(item.kind,'UTF8')=pg_catalog.convert_to('job','UTF8') THEN
                IF item.direct_path IS DISTINCT FROM TRUE OR item.half_present IS DISTINCT FROM FALSE
                   OR item.half_work_id IS NOT NULL OR item.half_subscription IS NOT NULL
                   OR item.half_event IS NOT NULL OR item.half_digest IS NOT NULL
                   OR item.half_envelope IS NOT NULL OR item.half_replay IS NOT NULL THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission job projection';
                END IF;
            ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission candidate kind';
            END IF;
            IF item.key_path THEN
                IF p_idempotency_key IS NULL
                   OR pg_catalog.convert_to(item.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('inbox','UTF8')
                   OR item.namespace IS DISTINCT FROM p_namespace OR item.command_type IS DISTINCT FROM p_command_type
                   OR pg_catalog.sha256(item.subscription_id) IS DISTINCT FROM pg_catalog.sha256(p_subscription_id)
                   OR pg_catalog.sha256(item.scope_evidence) IS DISTINCT FROM pg_catalog.sha256(p_scope_evidence)
                   OR pg_catalog.sha256(item.idempotency_key) IS DISTINCT FROM pg_catalog.sha256(p_idempotency_key) THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission key path';
                END IF;
            END IF;
            IF item.event_path THEN
                IF item.half_present IS DISTINCT FROM TRUE OR item.half_subscription IS DISTINCT FROM p_subscription_id
                   OR item.half_digest IS DISTINCT FROM pg_catalog.sha256(p_event_id) THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission event path';
                END IF;
            END IF;
            present_count:=present_count+1;
            IF present_count=1 THEN saved_one:=item;
            ELSIF present_count=2 THEN saved_two:=item;
            ELSIF present_count=3 THEN saved_three:=item;
            ELSE RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission family cardinality'; END IF;
        END LOOP;
        -- No conflict/capacity diagnosis until EVERY selected E15/half passed.
        IF selected_count<1 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing admission capture';
        END IF;
        IF selected_count IS DISTINCT FROM item.captured_count OR direct_seen<>1
           OR key_seen IS DISTINCT FROM item.raw_key_count OR event_seen IS DISTINCT FROM item.raw_event_count
           OR final_own_ids IS DISTINCT FROM own_ids THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='changed own admission membership';
        END IF;
        IF capture_pass=2 THEN
            IF present_count=0 OR pg_catalog.cardinality(final_own_ids)>0 THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid lost reservation winner';
            END IF;
            RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='foreign admission reservation conflict';
        END IF;
        -- P4: full immutable identity/intent/replay/event, never digest equality.
        IF present_count>1 THEN
            RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='split admission identity';
        END IF;
        IF present_count=1 THEN
            item:=saved_one;
            IF ROW(pg_catalog.convert_to(item.kind,'UTF8'),item.subscription_id,item.namespace,item.command_type,
                   item.scope_evidence,item.idempotency_key,item.canonical_version,item.schema_version_decimal,
                   item.scope_application,item.scope_tenant,item.scope_owner,item.intent_evidence,item.semantic_input,
                   item.replay_input,item.protected_binding,pg_catalog.convert_to(item.replay_policy,'UTF8'),
                   item.max_attempts,item.deadline,item.original_available_at,
                   item.half_event,item.half_envelope,item.half_replay)
               IS DISTINCT FROM
               ROW(pg_catalog.convert_to(p_kind,'UTF8'),p_subscription_id,p_namespace,p_command_type,
                   p_scope_evidence,p_idempotency_key,p_canonical_version,p_schema_version_decimal,
                   p_scope_application,p_scope_tenant,p_scope_owner,p_intent_evidence,p_semantic_input,
                   p_replay_input,p_protected_binding,pg_catalog.convert_to(p_replay_policy,'UTF8'),
                   p_max_attempts,p_deadline,p_original_available_at,
                   p_event_id,p_envelope_evidence,p_event_replay_input) THEN
                RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='admission immutable intent conflict';
            END IF;
            delivery_time:=pg_catalog.clock_timestamp();
            IF modkit_events._instant_bytes(delivery_time) IS NULL THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unsupported admission delivery time';
            END IF;
            INSERT INTO modkit_events.delivery_history AS delivery
                (work_id,broker_reference,transport_observation,recorded_at)
                VALUES(item.work_id,p_broker_reference,p_transport_observation,delivery_time)
                RETURNING delivery.history_id INTO generated_id;
            GET DIAGNOSTICS affected=ROW_COUNT;
            IF affected<>1 OR generated_id IS NULL OR generated_id<=0 THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission delivery receipt';
            END IF;
            RETURN QUERY SELECT item.work_id,FALSE;
            RETURN;
        END IF;

        -- P5: only the validated empty family reaches capacity/reservation.
        IF parent_row.nonterminal_count=parent_row.capacity THEN
            RAISE EXCEPTION USING ERRCODE='PZ007',MESSAGE='subscription capacity exhausted';
        END IF;
        creation_time:=pg_catalog.clock_timestamp();
        IF modkit_events._instant_bytes(creation_time) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unsupported admission creation time';
        END IF;
        INSERT INTO modkit_events.work AS reservation
            (work_id,kind,subscription_id,namespace,command_type,schema_version_decimal,runnable_version,
             canonical_version,scope_evidence,scope_application,scope_tenant,scope_owner,idempotency_key,
             intent_evidence,semantic_input,replay_input,protected_binding,replay_policy,max_attempts,
             deadline,original_available_at,state,cancellation_requested,token,ownership_revision,
             lease_until,available_at,cycle,attempt_count,dispatch_id,result,created_at,updated_at,
             success_origin,completion_guard_id,final_fence_at,completion_result_digest,
             resolution_operation_id,terminal_resolution_operation_id)
            VALUES(p_work_id,p_kind,p_subscription_id,p_namespace,p_command_type,p_schema_version_decimal,runnable,
             p_canonical_version,p_scope_evidence,p_scope_application,p_scope_tenant,p_scope_owner,p_idempotency_key,
             p_intent_evidence,p_semantic_input,p_replay_input,p_protected_binding,p_replay_policy,p_max_attempts,
             p_deadline,p_original_available_at,initial_state,FALSE,NULL,0,NULL,p_original_available_at,1,0,
             NULL,NULL,creation_time,creation_time,NULL,NULL,NULL,NULL,NULL,NULL)
            ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS affected=ROW_COUNT;
        IF affected=1 THEN EXIT;
        ELSIF affected<>0 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission reservation count'; END IF;
        -- A unique check can wait on a winner absent from its INSERT snapshot.
        -- Only the next loop's NEW capture observes it; no retry/reinsert/locks.
    END LOOP;

    -- P7: new Work is owned. Trigger's work lock is self-owned, parent held.
    intake_time:=pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(intake_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unsupported admission intake time';
    END IF;
    UPDATE modkit_events.work AS stored SET updated_at=intake_time WHERE stored.work_id=p_work_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing reserved admission'; END IF;
    INSERT INTO modkit_events.inbox(work_id,subscription_id,event_id,envelope_evidence,replay_input)
        VALUES(p_work_id,p_subscription_id,p_event_id,p_envelope_evidence,p_event_replay_input);
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission subtype count'; END IF;
    UPDATE modkit_events.subscriptions AS stored SET nonterminal_count=parent_row.nonterminal_count+1
        WHERE stored.subscription_id=p_subscription_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing admission parent'; END IF;
    INSERT INTO modkit_events.work_history AS history
        (work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(p_work_id,1,0,intake_code,intake_code,NULL,0,''::pg_catalog.bytea,intake_time)
        RETURNING history.history_id INTO generated_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 OR generated_id IS NULL OR generated_id<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission intake receipt';
    END IF;
    INSERT INTO modkit_events.delivery_history AS delivery
        (work_id,broker_reference,transport_observation,recorded_at)
        VALUES(p_work_id,p_broker_reference,p_transport_observation,intake_time)
        RETURNING delivery.history_id INTO generated_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 OR generated_id IS NULL OR generated_id<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid admission delivery receipt';
    END IF;
    -- Staged receipt only; no same-command STABLE postwrite read or commit claim.
    RETURN QUERY SELECT p_work_id,TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e03(pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.timestamptz,pg_catalog.timestamptz,pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bool,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

-- Segment13: selected structural outbox reader. Still NOT_READY.
CREATE FUNCTION modkit_events.e28(p_event_id pg_catalog.bytea)
RETURNS TABLE(
    event_id pg_catalog.bytea,canonical_version pg_catalog.int4,
    envelope_evidence pg_catalog.bytea,replay_input pg_catalog.bytea,
    state pg_catalog.text,token pg_catalog.uuid,ownership_revision pg_catalog.int8,
    lease_until pg_catalog.timestamptz,intent_id pg_catalog.uuid,
    receipt pg_catalog.bytea,outcome_evidence pg_catalog.bytea,
    created_at pg_catalog.timestamptz,updated_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    captured pg_catalog.record;
    stored modkit_events.outbox%ROWTYPE;
    envelope pg_catalog.bytea;
    fields pg_catalog.bytea[];
    owned pg_catalog.bool;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid outbox reader arguments';
    END IF;
    -- One calling-query snapshot; digest discovers aliases, full ID never filters
    -- them away. Preserve an absent anchor and raw PK/cardinality sentinels.
    WITH candidates AS MATERIALIZED (
        SELECT item.* FROM modkit_events.outbox AS item
         WHERE item.event_digest=pg_catalog.sha256(p_event_id)
    )
    SELECT (SELECT pg_catalog.count(*) FROM candidates) AS selected_count,
           candidate.event_digest IS NOT NULL AS present,candidate AS stored_row
      INTO captured
      FROM (VALUES(p_event_id)) AS requested(id)
      LEFT JOIN candidates AS candidate ON TRUE;
    IF captured.selected_count IS NULL OR captured.selected_count<0 OR captured.selected_count>1
       OR captured.present IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid outbox reader cardinality';
    END IF;
    IF captured.selected_count=0 THEN
        IF captured.present IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid absent outbox sentinel';
        END IF;
        RETURN;
    END IF;
    IF captured.present IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing selected outbox record';
    END IF;
    stored:=captured.stored_row;
    -- No relation access below. Validate the complete selected row before
    -- request representability, using only existing immutable byte/time helpers.
    IF modkit_events._utf8_valid(stored.event_id,256,TRUE) IS NOT TRUE
       OR stored.event_digest IS DISTINCT FROM pg_catalog.sha256(stored.event_id)
       OR stored.event_digest IS DISTINCT FROM pg_catalog.sha256(p_event_id)
       OR stored.canonical_version IS DISTINCT FROM 1
       OR stored.envelope_evidence IS NULL OR pg_catalog.octet_length(stored.envelope_evidence)<1
       OR pg_catalog.octet_length(stored.envelope_evidence)>1048576
       OR stored.replay_input IS NULL OR pg_catalog.octet_length(stored.replay_input)<1
       OR pg_catalog.octet_length(stored.replay_input)>1048576
       OR (pg_catalog.convert_to(stored.state,'UTF8') IN
           (pg_catalog.convert_to('pending','UTF8'),pg_catalog.convert_to('claimed','UTF8'),
            pg_catalog.convert_to('publishing','UTF8'),pg_catalog.convert_to('published','UTF8'),
            pg_catalog.convert_to('rejected','UTF8'),pg_catalog.convert_to('held','UTF8'))) IS NOT TRUE
       OR stored.ownership_revision IS NULL OR stored.ownership_revision<0
       OR modkit_events._instant_bytes(stored.created_at) IS NULL
       OR modkit_events._instant_bytes(stored.updated_at) IS NULL
       OR (stored.lease_until IS NOT NULL AND modkit_events._instant_bytes(stored.lease_until) IS NULL)
       OR (stored.receipt IS NOT NULL AND pg_catalog.octet_length(stored.receipt)>4096)
       OR (stored.outcome_evidence IS NOT NULL AND pg_catalog.octet_length(stored.outcome_evidence)>1048576) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid outbox record';
    END IF;
    owned:=pg_catalog.convert_to(stored.state,'UTF8') IN
        (pg_catalog.convert_to('claimed','UTF8'),pg_catalog.convert_to('publishing','UTF8'));
    IF owned IS DISTINCT FROM (stored.token IS NOT NULL)
       OR owned IS DISTINCT FROM (stored.lease_until IS NOT NULL)
       OR (owned AND stored.ownership_revision<=0)
       OR ((pg_catalog.convert_to(stored.state,'UTF8') IN
           (pg_catalog.convert_to('pending','UTF8'),pg_catalog.convert_to('claimed','UTF8')))
           IS DISTINCT FROM (stored.intent_id IS NULL)) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid outbox ownership';
    END IF;
    envelope:=modkit_events._event_replay_frame(stored.replay_input);
    IF envelope IS NULL OR envelope IS DISTINCT FROM stored.envelope_evidence THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid outbox event envelope';
    END IF;
    fields:=modkit_events._record_fields(envelope,pg_catalog.convert_to('event-envelope','UTF8'),5);
    IF fields IS NULL OR fields[1] IS DISTINCT FROM stored.event_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid outbox full event identity';
    END IF;
    -- Coherent different-full-ID digest hit is unrepresentable in the exact
    -- E28 decoder; integrity has priority over this identity conflict.
    IF stored.event_id IS DISTINCT FROM p_event_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='outbox event identity conflict';
    END IF;
    -- Structural observation only: no repair/history witness, clock comparison,
    -- monotonic-time rule, commit certainty or external publication certificate.
    RETURN QUERY SELECT stored.event_id,stored.canonical_version,stored.envelope_evidence,stored.replay_input,
        stored.state,stored.token,stored.ownership_revision,stored.lease_until,stored.intent_id,
        stored.receipt,stored.outcome_evidence,stored.created_at,stored.updated_at;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e28(pg_catalog.bytea) FROM PUBLIC;

-- Segment14: selected E02 lawful enqueue. Still NOT_READY.
-- Cooperative outbox writers retain full identity/replay/creation and do not
-- delete retained identities; callers own prior locks and transaction outcome.
CREATE FUNCTION modkit_events.e02(
    p_event_id pg_catalog.bytea,p_canonical_version pg_catalog.int4,
    p_envelope_evidence pg_catalog.bytea,p_replay_input pg_catalog.bytea
)
RETURNS TABLE(inserted pg_catalog.bool)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    envelope pg_catalog.bytea;
    fields pg_catalog.bytea[];
    created pg_catalog.bool:=FALSE;
    affected pg_catalog.int8;
    history_id pg_catalog.int8;
    creation_time pg_catalog.timestamptz;
    enqueue_time pg_catalog.timestamptz;
    captured pg_catalog.record;
BEGIN
    -- P0: complete EventInput before any relation access, clock or write.
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE
       OR p_canonical_version IS DISTINCT FROM 1
       OR p_envelope_evidence IS NULL OR pg_catalog.octet_length(p_envelope_evidence)<1
       OR pg_catalog.octet_length(p_envelope_evidence)>1048576
       OR p_replay_input IS NULL OR pg_catalog.octet_length(p_replay_input)<1
       OR pg_catalog.octet_length(p_replay_input)>1048576 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid enqueue arguments';
    END IF;
    envelope:=modkit_events._event_replay_frame(p_replay_input);
    IF envelope IS NULL OR envelope IS DISTINCT FROM p_envelope_evidence THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid enqueue event envelope';
    END IF;
    fields:=modkit_events._record_fields(envelope,pg_catalog.convert_to('event-envelope','UTF8'),5);
    IF fields IS NULL OR fields[1] IS DISTINCT FROM p_event_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid enqueue full event identity';
    END IF;

    -- P1: one digest identity mutex, never hide an alias with full-ID filtering.
    PERFORM stored.event_digest FROM modkit_events.outbox AS stored
        WHERE stored.event_digest=pg_catalog.sha256(p_event_id) FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        -- P2: only absence reaches one reservation. T0 is retained creation,
        -- not a final fence and may precede a uniqueness wait.
        creation_time:=pg_catalog.clock_timestamp();
        IF modkit_events._instant_bytes(creation_time) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unsupported enqueue creation time';
        END IF;
        INSERT INTO modkit_events.outbox AS reservation
            (event_id,canonical_version,envelope_evidence,replay_input,state,token,
             ownership_revision,lease_until,intent_id,receipt,outcome_evidence,created_at,updated_at)
            VALUES(p_event_id,p_canonical_version,p_envelope_evidence,p_replay_input,'pending',NULL,
                0,NULL,NULL,NULL,NULL,creation_time,creation_time)
            ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS affected=ROW_COUNT;
        IF affected=1 THEN
            created:=TRUE;
        ELSIF affected=0 THEN
            -- P3: a unique wait can observe a winner invisible to its INSERT
            -- snapshot. One following mutex command, then a separate fresh read.
            PERFORM stored.event_digest FROM modkit_events.outbox AS stored
                WHERE stored.event_digest=pg_catalog.sha256(p_event_id) FOR NO KEY UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing enqueue reservation winner';
            END IF;
        ELSE
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid enqueue reservation cardinality';
        END IF;
    END IF;

    IF NOT created THEN
        -- P4: existing/loser only. Materialize ONE E28 invocation in this NEW
        -- calling-query snapshot after the mutex wait; all integrity precedes
        -- full immutable comparison. Never use it to reread our new insertion.
        WITH checked AS MATERIALIZED (
            SELECT observed.* FROM modkit_events.e28(p_event_id) AS observed
        )
        SELECT (SELECT pg_catalog.count(*) FROM checked) AS selected_count,
               observed.event_id IS NOT NULL AS present,observed.*
          INTO captured
          FROM (VALUES(TRUE)) AS requested(anchor)
          LEFT JOIN checked AS observed ON TRUE;
        IF captured.selected_count IS DISTINCT FROM 1 OR captured.present IS DISTINCT FROM TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid enqueue winner observation';
        END IF;
        IF ROW(captured.event_id,captured.canonical_version,captured.envelope_evidence,captured.replay_input)
            IS DISTINCT FROM ROW(p_event_id,p_canonical_version,p_envelope_evidence,p_replay_input) THEN
            RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='enqueue immutable input conflict';
        END IF;
        -- Exact duplicate preserves every state/time/history/sequence field.
        RETURN QUERY SELECT FALSE;
        RETURN;
    END IF;

    -- P5: successful reservation owns this new row. T1 follows any unique wait;
    -- validate before history allocation, without requiring T1 >= T0.
    enqueue_time:=pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(enqueue_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unsupported enqueue history time';
    END IF;
    UPDATE modkit_events.outbox AS stored SET updated_at=enqueue_time
        WHERE stored.event_digest=pg_catalog.sha256(p_event_id);
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing new enqueue reservation';
    END IF;
    INSERT INTO modkit_events.publication_history AS history
        (event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
        VALUES(p_event_id,NULL,NULL,'enqueue',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,enqueue_time)
        RETURNING history.history_id INTO history_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 OR history_id IS NULL OR history_id<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid enqueue history receipt';
    END IF;
    -- Staged only: caller owns commit/rollback and uncertain outcome resolution.
    RETURN QUERY SELECT TRUE;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e02(pg_catalog.bytea,pg_catalog.int4,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

-- E04: source candidate; separate SQL/runtime qualification remains required.
CREATE FUNCTION modkit_events.e04(
    p_namespace pg_catalog.bytea,
    p_kind pg_catalog.text,
    p_command_types pg_catalog.bytea[],
    p_schema_versions pg_catalog.int4[],
    p_limit pg_catalog.int4,
    p_lease_seconds pg_catalog.float8,
    p_scan_after pg_catalog.uuid,
    p_discovery_budget pg_catalog.int4)
RETURNS TABLE(record_type pg_catalog.text, visited pg_catalog.int4, next_cursor pg_catalog.uuid, pass_exhausted pg_catalog.bool,

    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE

    discovered pg_catalog.record;
    captured pg_catalog.record;
    w modkit_events.work%ROWTYPE;
    fresh_work modkit_events.work%ROWTYPE;
    expected_work modkit_events.work%ROWTYPE;
    updated_work modkit_events.work%ROWTYPE;
    subscription_row modkit_events.subscriptions%ROWTYPE;
    is_job pg_catalog.bool;
    final_time pg_catalog.timestamptz;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;

    lease_wire pg_catalog.bytea;
    exponent_bits pg_catalog.int4;
    significand pg_catalog.int8;
    numerator pg_catalog.numeric;
    denominator pg_catalog.numeric;
    byte_index pg_catalog.int4;
    bit_index pg_catalog.int4;
    lease_us pg_catalog.int8;
    candidate_lease pg_catalog.timestamptz;

    pair_count pg_catalog.int4;
    command_lower pg_catalog.int4;
    version_lower pg_catalog.int4;
    pair_index pg_catalog.int4;
    prior_index pg_catalog.int4;
    capable pg_catalog.bool;
    cursor_value pg_catalog.uuid;
    visited_count pg_catalog.int4;
    item_count pg_catalog.int4;
    exhausted_value pg_catalog.bool;
    next_revision pg_catalog.int8;
    claim_token pg_catalog.uuid;
    emitted_rows modkit_events.work[];
    emitted modkit_events.work%ROWTYPE;
BEGIN

    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;

    IF modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE
       OR (pg_catalog.convert_to(p_kind,'UTF8') IN
          (pg_catalog.convert_to('job','UTF8'),pg_catalog.convert_to('inbox','UTF8'))) IS NOT TRUE
       OR p_command_types IS NULL OR p_schema_versions IS NULL
       OR pg_catalog.array_ndims(p_command_types) IS DISTINCT FROM 1
       OR pg_catalog.array_ndims(p_schema_versions) IS DISTINCT FROM 1
       OR pg_catalog.cardinality(p_command_types) NOT BETWEEN 1 AND 256
       OR pg_catalog.cardinality(p_schema_versions) IS DISTINCT FROM pg_catalog.cardinality(p_command_types)
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256
       OR p_discovery_budget IS NULL OR p_discovery_budget NOT BETWEEN 1 AND 4096
       OR p_discovery_budget<p_limit
       OR (p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid acquisition arguments';
    END IF;
    pair_count := pg_catalog.cardinality(p_command_types);
    command_lower := pg_catalog.array_lower(p_command_types,1);
    version_lower := pg_catalog.array_lower(p_schema_versions,1);
    FOR pair_index IN 1..pair_count LOOP
        IF modkit_events._utf8_valid(p_command_types[command_lower+(pair_index-1)],256,TRUE) IS NOT TRUE
           OR p_schema_versions[version_lower+(pair_index-1)] IS NULL
           OR p_schema_versions[version_lower+(pair_index-1)]<=0 THEN
            RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid zipped capability';
        END IF;
        FOR prior_index IN 1..pair_index-1 LOOP
            IF p_command_types[command_lower+(pair_index-1)]=p_command_types[command_lower+(prior_index-1)]
               AND p_schema_versions[version_lower+(pair_index-1)]=p_schema_versions[version_lower+(prior_index-1)] THEN
                RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='duplicate zipped capability';
            END IF;
        END LOOP;
    END LOOP;

    -- Exact ceil of the represented positive binary64 duration, not float multiplication.
    lease_wire := pg_catalog.float8send(p_lease_seconds);
    IF pg_catalog.octet_length(lease_wire)<>8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected float8 representation';
    END IF;
    exponent_bits := ((pg_catalog.get_byte(lease_wire,0)&127)<<4)|(pg_catalog.get_byte(lease_wire,1)>>4);
    IF exponent_bits <= 1002 THEN
        lease_us := 1;
    ELSE
        significand := (pg_catalog.get_byte(lease_wire,1)&15)::pg_catalog.int8;
        FOR byte_index IN 2..7 LOOP
            significand := significand*256+pg_catalog.get_byte(lease_wire,byte_index);
        END LOOP;
        significand := significand+4503599627370496;
        numerator := significand::pg_catalog.numeric * 1000000::pg_catalog.numeric;
        denominator := 1::pg_catalog.numeric;
        FOR bit_index IN 1..(1075-exponent_bits) LOOP
            denominator := denominator*2;
        END LOOP;
        lease_us := pg_catalog.div(numerator+denominator-1,denominator)::pg_catalog.int8;
    END IF;
    IF lease_us IS NULL OR lease_us<1 OR lease_us>3600000000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid quantized lease';
    END IF;

    cursor_value := p_scan_after;
    visited_count := 0;
    item_count := 0;
    exhausted_value := FALSE;
    emitted_rows := ARRAY[]::modkit_events.work[];
    WHILE visited_count<p_discovery_budget AND item_count<p_limit LOOP
        -- Raw identity progress is bounded and does not certify skipped rows.
        IF cursor_value IS NULL THEN
            SELECT wr.work_id,wr.kind,wr.subscription_id,wr.state,wr.command_type,wr.runnable_version
              INTO discovered FROM modkit_events.work AS wr
              WHERE wr.namespace=p_namespace AND wr.kind=p_kind
                AND wr.kind COLLATE pg_catalog."C"=p_kind COLLATE pg_catalog."C"
              ORDER BY wr.work_id LIMIT 1;
        ELSE
            SELECT wr.work_id,wr.kind,wr.subscription_id,wr.state,wr.command_type,wr.runnable_version
              INTO discovered FROM modkit_events.work AS wr
              WHERE wr.namespace=p_namespace AND wr.kind=p_kind AND wr.work_id>cursor_value
                AND wr.kind COLLATE pg_catalog."C"=p_kind COLLATE pg_catalog."C"
              ORDER BY wr.work_id LIMIT 1;
        END IF;
        IF NOT FOUND THEN
            exhausted_value := TRUE;
            EXIT;
        END IF;
        visited_count := visited_count+1;
        cursor_value := discovered.work_id;
        IF (discovered.state COLLATE pg_catalog."C" IN ('queued','retry_waiting')) IS NOT TRUE THEN
            CONTINUE;
        END IF;

        capable := FALSE;
        FOR pair_index IN 1..pair_count LOOP
            IF discovered.command_type=p_command_types[command_lower+(pair_index-1)]
               AND discovered.runnable_version=p_schema_versions[version_lower+(pair_index-1)] THEN
                capable := TRUE;
                EXIT;
            END IF;
        END LOOP;

        IF NOT capable THEN CONTINUE; END IF;

    IF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('job','UTF8') THEN
        is_job := TRUE;
        IF discovered.subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSIF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('inbox','UTF8') THEN
        is_job := FALSE;
        IF modkit_events._utf8_valid(discovered.subscription_id,256,TRUE) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;

        IF NOT is_job THEN
            PERFORM parent.subscription_id FROM modkit_events.subscriptions AS parent
                WHERE parent.subscription_id=discovered.subscription_id FOR NO KEY UPDATE OF parent SKIP LOCKED;
            IF NOT FOUND THEN
                IF NOT EXISTS(SELECT 1 FROM modkit_events.subscriptions AS parent
                              WHERE parent.subscription_id=discovered.subscription_id) THEN
                    RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
                END IF;
                CONTINUE;
            END IF;
        END IF;
        SELECT stored.* INTO w FROM modkit_events.work AS stored
            WHERE stored.work_id=discovered.work_id FOR NO KEY UPDATE OF stored SKIP LOCKED;
        IF NOT FOUND THEN
            IF NOT EXISTS(SELECT 1 FROM modkit_events.work AS stored WHERE stored.work_id=discovered.work_id) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing discovered work';
            END IF;
            CONTINUE;
        END IF;

    IF w.work_id IS DISTINCT FROM discovered.work_id
       OR pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(discovered.kind,'UTF8')
       OR w.subscription_id IS DISTINCT FROM discovered.subscription_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work identity changed during acquisition';
    END IF;

    -- All entity locks are held. E15 and both preimages share this query snapshot.
    SELECT stored AS current_work,parent AS current_parent,checked.*
      INTO captured
      FROM modkit_events.work AS stored
      CROSS JOIN LATERAL modkit_events.e15(stored.work_id) AS checked
      LEFT JOIN modkit_events.subscriptions AS parent ON parent.subscription_id=stored.subscription_id
      WHERE stored.work_id=w.work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full work observation';
    END IF;
    fresh_work := captured.current_work;
    subscription_row := captured.current_parent;
    IF fresh_work IS DISTINCT FROM w
       OR pg_catalog.convert_to(fresh_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.kind,'UTF8')
       OR pg_catalog.convert_to(fresh_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.state,'UTF8')
       OR pg_catalog.convert_to(fresh_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.replay_policy,'UTF8')
       OR captured.work_id IS DISTINCT FROM w.work_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work changed under held locks';
    END IF;
    w := fresh_work;

        IF w.namespace IS DISTINCT FROM p_namespace THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work partition changed during acquisition';
        END IF;
        IF (w.state COLLATE pg_catalog."C" IN ('queued','retry_waiting')) IS NOT TRUE THEN
            CONTINUE;
        END IF;
    IF NOT is_job AND (subscription_row.subscription_id IS DISTINCT FROM w.subscription_id
       OR subscription_row.nonterminal_count IS NULL OR subscription_row.nonterminal_count<=0) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid nonterminal parent count';
    END IF;

        capable := FALSE;
        FOR pair_index IN 1..pair_count LOOP
            IF w.command_type=p_command_types[command_lower+(pair_index-1)]
               AND w.runnable_version=p_schema_versions[version_lower+(pair_index-1)] THEN
                capable := TRUE;
                EXIT;
            END IF;
        END LOOP;

        -- Leave a successor revision for completion or deferral.
        IF NOT capable OR w.ownership_revision>=9223372036854775806::pg_catalog.int8 THEN
            CONTINUE;
        END IF;

    final_time := pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(final_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
    END IF;

        IF w.cancellation_requested IS DISTINCT FROM FALSE OR w.dispatch_id IS NOT NULL
           OR w.available_at>final_time OR (w.deadline IS NOT NULL AND final_time>=w.deadline)
           OR w.attempt_count>=w.max_attempts THEN
            CONTINUE;
        END IF;
        candidate_lease := final_time+(INTERVAL '1 microsecond' * lease_us::pg_catalog.float8);
        IF modkit_events._instant_bytes(candidate_lease) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='lease timestamp outside supported domain';
        END IF;
        IF w.deadline IS NOT NULL AND candidate_lease>w.deadline THEN
            candidate_lease := w.deadline;
        END IF;
        IF candidate_lease<=final_time OR modkit_events._instant_bytes(candidate_lease) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid selected lease';
        END IF;
        next_revision := w.ownership_revision+1;
        claim_token := pg_catalog.gen_random_uuid();
        IF claim_token IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing ownership token';
        END IF;
        expected_work := w;
        expected_work.state := 'claimed';
        expected_work.token := claim_token;
        expected_work.ownership_revision := next_revision;
        expected_work.lease_until := candidate_lease;
        expected_work.updated_at := final_time;
        UPDATE modkit_events.work AS stored SET state='claimed',token=claim_token,
            ownership_revision=next_revision,lease_until=candidate_lease,updated_at=final_time
            WHERE stored.work_id=w.work_id
            RETURNING stored.* INTO updated_work;

    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR updated_work IS DISTINCT FROM expected_work
       OR pg_catalog.convert_to(updated_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.kind,'UTF8')
       OR pg_catalog.convert_to(updated_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.state,'UTF8')
       OR pg_catalog.convert_to(updated_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.replay_policy,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work update postimage mismatch';
    END IF;

    INSERT INTO modkit_events.work_history AS stored
        (work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(updated_work.work_id,updated_work.cycle,updated_work.attempt_count,
               'claim','claim',updated_work.token,updated_work.ownership_revision,''::pg_catalog.bytea,final_time)
        RETURNING stored.history_id INTO history_id_value;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid history insertion receipt';
    END IF;

        emitted_rows := pg_catalog.array_append(emitted_rows,updated_work);
        item_count := item_count+1;
    END LOOP;
    IF visited_count=p_discovery_budget OR item_count=p_limit THEN
        exhausted_value := FALSE;
    END IF;
    -- No STABLE post-write reader: these are already validated, retained postimages.
    RETURN QUERY SELECT 'header'::pg_catalog.text,visited_count,cursor_value,exhausted_value,
        NULL::pg_catalog.uuid,NULL::pg_catalog.text,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.int4,NULL::pg_catalog.int4,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.text,NULL::pg_catalog.int4,NULL::pg_catalog.timestamptz,NULL::pg_catalog.timestamptz,NULL::pg_catalog.text,NULL::pg_catalog.bool,NULL::pg_catalog.uuid,NULL::pg_catalog.int8,NULL::pg_catalog.timestamptz,NULL::pg_catalog.timestamptz,NULL::pg_catalog.int4,NULL::pg_catalog.int4,NULL::pg_catalog.uuid,NULL::pg_catalog.bytea,NULL::pg_catalog.timestamptz,NULL::pg_catalog.timestamptz,NULL::pg_catalog.text,NULL::pg_catalog.uuid,NULL::pg_catalog.timestamptz,NULL::pg_catalog.bytea,NULL::pg_catalog.uuid,NULL::pg_catalog.uuid,NULL::pg_catalog.bool,NULL::pg_catalog.uuid,NULL::pg_catalog.text,NULL::pg_catalog.uuid,NULL::pg_catalog.int8,NULL::pg_catalog.int4,NULL::pg_catalog.int4,NULL::pg_catalog.uuid,NULL::pg_catalog.text,NULL::pg_catalog.timestamptz,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.text,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.xid8,NULL::pg_catalog.timestamptz;
    FOREACH emitted IN ARRAY emitted_rows LOOP
        RETURN QUERY SELECT 'item'::pg_catalog.text,NULL::pg_catalog.int4,NULL::pg_catalog.uuid,NULL::pg_catalog.bool,
            emitted.work_id,emitted.kind,emitted.subscription_id,emitted.namespace,emitted.command_type,emitted.schema_version_decimal,emitted.runnable_version,emitted.canonical_version,emitted.scope_evidence,emitted.scope_application,emitted.scope_tenant,emitted.scope_owner,emitted.idempotency_key,emitted.intent_evidence,emitted.semantic_input,emitted.replay_input,emitted.protected_binding,emitted.replay_policy,emitted.max_attempts,emitted.deadline,emitted.original_available_at,emitted.state,emitted.cancellation_requested,emitted.token,emitted.ownership_revision,emitted.lease_until,emitted.available_at,emitted.cycle,emitted.attempt_count,emitted.dispatch_id,emitted.result,emitted.created_at,emitted.updated_at,emitted.success_origin,emitted.completion_guard_id,emitted.final_fence_at,emitted.completion_result_digest,emitted.resolution_operation_id,emitted.terminal_resolution_operation_id,FALSE::pg_catalog.bool,NULL::pg_catalog.uuid,NULL::pg_catalog.text,NULL::pg_catalog.uuid,NULL::pg_catalog.int8,NULL::pg_catalog.int4,NULL::pg_catalog.int4,NULL::pg_catalog.uuid,NULL::pg_catalog.text,NULL::pg_catalog.timestamptz,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.text,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,NULL::pg_catalog.xid8,NULL::pg_catalog.timestamptz;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e04(pg_catalog.bytea,pg_catalog.text,pg_catalog.bytea[],pg_catalog.int4[],pg_catalog.int4,pg_catalog.float8,pg_catalog.uuid,pg_catalog.int4) FROM PUBLIC;

-- E05: source candidate; separate SQL/runtime qualification remains required.
CREATE FUNCTION modkit_events.e05(
    p_work_id pg_catalog.uuid,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4,
    p_lease_seconds pg_catalog.float8)
RETURNS TABLE(lease_until pg_catalog.timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE

    discovered pg_catalog.record;
    captured pg_catalog.record;
    w modkit_events.work%ROWTYPE;
    fresh_work modkit_events.work%ROWTYPE;
    expected_work modkit_events.work%ROWTYPE;
    updated_work modkit_events.work%ROWTYPE;
    subscription_row modkit_events.subscriptions%ROWTYPE;
    is_job pg_catalog.bool;
    final_time pg_catalog.timestamptz;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;

    lease_wire pg_catalog.bytea;
    exponent_bits pg_catalog.int4;
    significand pg_catalog.int8;
    numerator pg_catalog.numeric;
    denominator pg_catalog.numeric;
    byte_index pg_catalog.int4;
    bit_index pg_catalog.int4;
    lease_us pg_catalog.int8;
    candidate_lease pg_catalog.timestamptz;
BEGIN

    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;

    IF p_work_id IS NULL OR p_token IS NULL OR p_ownership_revision IS NULL
       OR p_ownership_revision<=0 OR p_cycle IS DISTINCT FROM 1
       OR p_expected_attempt IS NULL OR p_expected_attempt NOT BETWEEN 0 AND 1000

       OR (p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid dispatch operation arguments';
    END IF;

    -- Exact ceil of the represented positive binary64 duration, not float multiplication.
    lease_wire := pg_catalog.float8send(p_lease_seconds);
    IF pg_catalog.octet_length(lease_wire)<>8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected float8 representation';
    END IF;
    exponent_bits := ((pg_catalog.get_byte(lease_wire,0)&127)<<4)|(pg_catalog.get_byte(lease_wire,1)>>4);
    IF exponent_bits <= 1002 THEN
        lease_us := 1;
    ELSE
        significand := (pg_catalog.get_byte(lease_wire,1)&15)::pg_catalog.int8;
        FOR byte_index IN 2..7 LOOP
            significand := significand*256+pg_catalog.get_byte(lease_wire,byte_index);
        END LOOP;
        significand := significand+4503599627370496;
        numerator := significand::pg_catalog.numeric * 1000000::pg_catalog.numeric;
        denominator := 1::pg_catalog.numeric;
        FOR bit_index IN 1..(1075-exponent_bits) LOOP
            denominator := denominator*2;
        END LOOP;
        lease_us := pg_catalog.div(numerator+denominator-1,denominator)::pg_catalog.int8;
    END IF;
    IF lease_us IS NULL OR lease_us<1 OR lease_us>3600000000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid quantized lease';
    END IF;

    SELECT stored.work_id,stored.kind,stored.subscription_id INTO discovered
        FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('job','UTF8') THEN
        is_job := TRUE;
        IF discovered.subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSIF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('inbox','UTF8') THEN
        is_job := FALSE;
        IF modkit_events._utf8_valid(discovered.subscription_id,256,TRUE) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;

    IF NOT is_job THEN
        PERFORM parent.subscription_id FROM modkit_events.subscriptions AS parent
            WHERE parent.subscription_id=discovered.subscription_id FOR NO KEY UPDATE OF parent;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
        END IF;
    END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored
        WHERE stored.work_id=p_work_id FOR NO KEY UPDATE OF stored;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    -- New command snapshot after the blocking lock; check raw Fence/state before E15.
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF w.work_id IS DISTINCT FROM discovered.work_id
       OR pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(discovered.kind,'UTF8')
       OR w.subscription_id IS DISTINCT FROM discovered.subscription_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work identity changed during acquisition';
    END IF;

    IF w.token IS DISTINCT FROM p_token OR w.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR w.cycle IS DISTINCT FROM p_cycle OR w.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF (w.state COLLATE pg_catalog."C" IN ('claimed','running')) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid work state';
    END IF;

    -- All entity locks are held. E15 and both preimages share this query snapshot.
    SELECT stored AS current_work,parent AS current_parent,checked.*
      INTO captured
      FROM modkit_events.work AS stored
      CROSS JOIN LATERAL modkit_events.e15(stored.work_id) AS checked
      LEFT JOIN modkit_events.subscriptions AS parent ON parent.subscription_id=stored.subscription_id
      WHERE stored.work_id=w.work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full work observation';
    END IF;
    fresh_work := captured.current_work;
    subscription_row := captured.current_parent;
    IF fresh_work IS DISTINCT FROM w
       OR pg_catalog.convert_to(fresh_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.kind,'UTF8')
       OR pg_catalog.convert_to(fresh_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.state,'UTF8')
       OR pg_catalog.convert_to(fresh_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.replay_policy,'UTF8')
       OR captured.work_id IS DISTINCT FROM w.work_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work changed under held locks';
    END IF;
    w := fresh_work;
    IF NOT is_job AND (subscription_row.subscription_id IS DISTINCT FROM w.subscription_id
       OR subscription_row.nonterminal_count IS NULL OR subscription_row.nonterminal_count<=0) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid nonterminal parent count';
    END IF;

    final_time := pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(final_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
    END IF;

    IF w.cancellation_requested IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work cancellation requested';
    END IF;
    IF w.deadline IS NOT NULL AND final_time>=w.deadline THEN
        RAISE EXCEPTION USING ERRCODE='PZ009',MESSAGE='work deadline reached';
    END IF;
    IF final_time>=w.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work lease expired';
    END IF;

    candidate_lease := final_time+(INTERVAL '1 microsecond' * lease_us::pg_catalog.float8);
    IF modkit_events._instant_bytes(candidate_lease) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='lease timestamp outside supported domain';
    END IF;
    IF candidate_lease<w.lease_until THEN
        candidate_lease := w.lease_until;
    END IF;
    IF w.deadline IS NOT NULL AND candidate_lease>w.deadline THEN
        candidate_lease := w.deadline;
    END IF;
    IF candidate_lease<=final_time OR modkit_events._instant_bytes(candidate_lease) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid renewed lease';
    END IF;
    expected_work := w;
    expected_work.lease_until := candidate_lease;
    expected_work.updated_at := final_time;
    UPDATE modkit_events.work AS stored SET lease_until=candidate_lease,updated_at=final_time
        WHERE stored.work_id=p_work_id
        RETURNING stored.* INTO updated_work;

    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR updated_work IS DISTINCT FROM expected_work
       OR pg_catalog.convert_to(updated_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.kind,'UTF8')
       OR pg_catalog.convert_to(updated_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.state,'UTF8')
       OR pg_catalog.convert_to(updated_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.replay_policy,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work update postimage mismatch';
    END IF;

    INSERT INTO modkit_events.work_history AS stored
        (work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(updated_work.work_id,updated_work.cycle,updated_work.attempt_count,
               'renew','renew',updated_work.token,updated_work.ownership_revision,''::pg_catalog.bytea,final_time)
        RETURNING stored.history_id INTO history_id_value;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid history insertion receipt';
    END IF;

    RETURN QUERY SELECT updated_work.lease_until;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e05(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.float8) FROM PUBLIC;

-- E06: source candidate; separate SQL/runtime qualification remains required.
CREATE FUNCTION modkit_events.e06(
    p_work_id pg_catalog.uuid,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4,
    p_dispatch_id pg_catalog.uuid,
    p_effect_id pg_catalog.bytea,
    p_request_evidence pg_catalog.bytea,
    p_provider_key_reference pg_catalog.bytea)
RETURNS TABLE(attempt pg_catalog.int4)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE

    discovered pg_catalog.record;
    captured pg_catalog.record;
    w modkit_events.work%ROWTYPE;
    fresh_work modkit_events.work%ROWTYPE;
    expected_work modkit_events.work%ROWTYPE;
    updated_work modkit_events.work%ROWTYPE;
    subscription_row modkit_events.subscriptions%ROWTYPE;
    is_job pg_catalog.bool;
    final_time pg_catalog.timestamptz;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;

    next_attempt pg_catalog.int4;
    dispatch_root pg_catalog.xid8;
BEGIN

    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;

    IF p_work_id IS NULL OR p_token IS NULL OR p_ownership_revision IS NULL
       OR p_ownership_revision<=0 OR p_cycle IS DISTINCT FROM 1
       OR p_expected_attempt IS NULL OR p_expected_attempt NOT BETWEEN 0 AND 1000

       OR p_dispatch_id IS NULL OR modkit_events._utf8_valid(p_effect_id,256,TRUE) IS NOT TRUE
       OR p_request_evidence IS NULL OR pg_catalog.octet_length(p_request_evidence)>1048576
       OR (p_provider_key_reference IS NOT NULL AND modkit_events._utf8_valid(p_provider_key_reference,256,TRUE) IS NOT TRUE) THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid dispatch operation arguments';
    END IF;

    SELECT stored.work_id,stored.kind,stored.subscription_id INTO discovered
        FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('job','UTF8') THEN
        is_job := TRUE;
        IF discovered.subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSIF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('inbox','UTF8') THEN
        is_job := FALSE;
        IF modkit_events._utf8_valid(discovered.subscription_id,256,TRUE) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;

    IF NOT is_job THEN
        PERFORM parent.subscription_id FROM modkit_events.subscriptions AS parent
            WHERE parent.subscription_id=discovered.subscription_id FOR NO KEY UPDATE OF parent;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
        END IF;
    END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored
        WHERE stored.work_id=p_work_id FOR NO KEY UPDATE OF stored;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    -- New command snapshot after the blocking lock; check raw Fence/state before E15.
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF w.work_id IS DISTINCT FROM discovered.work_id
       OR pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(discovered.kind,'UTF8')
       OR w.subscription_id IS DISTINCT FROM discovered.subscription_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work identity changed during acquisition';
    END IF;

    IF w.token IS DISTINCT FROM p_token OR w.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR w.cycle IS DISTINCT FROM p_cycle OR w.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF pg_catalog.convert_to(w.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('claimed','UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid work state';
    END IF;

    -- All entity locks are held. E15 and both preimages share this query snapshot.
    SELECT stored AS current_work,parent AS current_parent,checked.*
      INTO captured
      FROM modkit_events.work AS stored
      CROSS JOIN LATERAL modkit_events.e15(stored.work_id) AS checked
      LEFT JOIN modkit_events.subscriptions AS parent ON parent.subscription_id=stored.subscription_id
      WHERE stored.work_id=w.work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full work observation';
    END IF;
    fresh_work := captured.current_work;
    subscription_row := captured.current_parent;
    IF fresh_work IS DISTINCT FROM w
       OR pg_catalog.convert_to(fresh_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.kind,'UTF8')
       OR pg_catalog.convert_to(fresh_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.state,'UTF8')
       OR pg_catalog.convert_to(fresh_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.replay_policy,'UTF8')
       OR captured.work_id IS DISTINCT FROM w.work_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work changed under held locks';
    END IF;
    w := fresh_work;
    IF NOT is_job AND (subscription_row.subscription_id IS DISTINCT FROM w.subscription_id
       OR subscription_row.nonterminal_count IS NULL OR subscription_row.nonterminal_count<=0) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid nonterminal parent count';
    END IF;

    IF w.ownership_revision=9223372036854775807::pg_catalog.int8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='ownership revision exhausted';
    END IF;

    final_time := pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(final_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
    END IF;

    IF w.cancellation_requested IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work cancellation requested';
    END IF;
    IF w.deadline IS NOT NULL AND final_time>=w.deadline THEN
        RAISE EXCEPTION USING ERRCODE='PZ009',MESSAGE='work deadline reached';
    END IF;
    IF final_time>=w.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work lease expired';
    END IF;

    IF w.dispatch_id IS NOT NULL OR w.attempt_count>=w.max_attempts OR w.runnable_version IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid claimed dispatch composition';
    END IF;
    next_attempt := w.attempt_count+1;
    dispatch_root := pg_catalog.pg_current_xact_id();
    IF dispatch_root IS NULL OR dispatch_root<='0'::pg_catalog.xid8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid dispatch root';
    END IF;
    INSERT INTO modkit_events.attempts
        (work_id,cycle,attempt,dispatch_id,effect_id,request_evidence,provider_key_reference,
         dispatch_root_xid,outcome,evidence,recorded_at)
        VALUES(p_work_id,w.cycle,next_attempt,p_dispatch_id,p_effect_id,p_request_evidence,p_provider_key_reference,
               dispatch_root,'dispatched',''::pg_catalog.bytea,final_time);
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='attempt insertion cardinality';
    END IF;
    expected_work := w;
    expected_work.state := 'running';
    expected_work.attempt_count := next_attempt;
    expected_work.dispatch_id := p_dispatch_id;
    expected_work.updated_at := final_time;
    UPDATE modkit_events.work AS stored SET state='running',attempt_count=next_attempt,
        dispatch_id=p_dispatch_id,updated_at=final_time
        WHERE stored.work_id=p_work_id
        RETURNING stored.* INTO updated_work;

    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR updated_work IS DISTINCT FROM expected_work
       OR pg_catalog.convert_to(updated_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.kind,'UTF8')
       OR pg_catalog.convert_to(updated_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.state,'UTF8')
       OR pg_catalog.convert_to(updated_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.replay_policy,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work update postimage mismatch';
    END IF;

    INSERT INTO modkit_events.work_history AS stored
        (work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(updated_work.work_id,updated_work.cycle,updated_work.attempt_count,
               'dispatch','dispatch',updated_work.token,updated_work.ownership_revision,''::pg_catalog.bytea,final_time)
        RETURNING stored.history_id INTO history_id_value;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid history insertion receipt';
    END IF;

    RETURN QUERY SELECT updated_work.attempt_count;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e06(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.uuid,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;

-- E07: source candidate; separate SQL/runtime qualification remains required.
CREATE FUNCTION modkit_events.e07(
    p_work_id pg_catalog.uuid,
    p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,
    p_cycle pg_catalog.int4,
    p_expected_attempt pg_catalog.int4,
    p_available_at pg_catalog.timestamptz)
RETURNS TABLE(ok pg_catalog.bool)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE

    discovered pg_catalog.record;
    captured pg_catalog.record;
    w modkit_events.work%ROWTYPE;
    fresh_work modkit_events.work%ROWTYPE;
    expected_work modkit_events.work%ROWTYPE;
    updated_work modkit_events.work%ROWTYPE;
    subscription_row modkit_events.subscriptions%ROWTYPE;
    is_job pg_catalog.bool;
    final_time pg_catalog.timestamptz;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;

    next_revision pg_catalog.int8;
BEGIN

    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;

    IF p_work_id IS NULL OR p_token IS NULL OR p_ownership_revision IS NULL
       OR p_ownership_revision<=0 OR p_cycle IS DISTINCT FROM 1
       OR p_expected_attempt IS NULL OR p_expected_attempt NOT BETWEEN 0 AND 1000

       OR modkit_events._instant_bytes(p_available_at) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid dispatch operation arguments';
    END IF;

    SELECT stored.work_id,stored.kind,stored.subscription_id INTO discovered
        FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('job','UTF8') THEN
        is_job := TRUE;
        IF discovered.subscription_id IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSIF pg_catalog.convert_to(discovered.kind,'UTF8')=pg_catalog.convert_to('inbox','UTF8') THEN
        is_job := FALSE;
        IF modkit_events._utf8_valid(discovered.subscription_id,256,TRUE) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work parent shape';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work kind';
    END IF;

    IF NOT is_job THEN
        PERFORM parent.subscription_id FROM modkit_events.subscriptions AS parent
            WHERE parent.subscription_id=discovered.subscription_id FOR NO KEY UPDATE OF parent;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing work subscription';
        END IF;
    END IF;
    PERFORM stored.work_id FROM modkit_events.work AS stored
        WHERE stored.work_id=p_work_id FOR NO KEY UPDATE OF stored;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    -- New command snapshot after the blocking lock; check raw Fence/state before E15.
    SELECT stored.* INTO w FROM modkit_events.work AS stored WHERE stored.work_id=p_work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;

    IF w.work_id IS DISTINCT FROM discovered.work_id
       OR pg_catalog.convert_to(w.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(discovered.kind,'UTF8')
       OR w.subscription_id IS DISTINCT FROM discovered.subscription_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work identity changed during acquisition';
    END IF;

    IF w.token IS DISTINCT FROM p_token OR w.ownership_revision IS DISTINCT FROM p_ownership_revision
       OR w.cycle IS DISTINCT FROM p_cycle OR w.attempt_count IS DISTINCT FROM p_expected_attempt THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale work fence';
    END IF;
    IF pg_catalog.convert_to(w.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to('claimed','UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid work state';
    END IF;

    -- All entity locks are held. E15 and both preimages share this query snapshot.
    SELECT stored AS current_work,parent AS current_parent,checked.*
      INTO captured
      FROM modkit_events.work AS stored
      CROSS JOIN LATERAL modkit_events.e15(stored.work_id) AS checked
      LEFT JOIN modkit_events.subscriptions AS parent ON parent.subscription_id=stored.subscription_id
      WHERE stored.work_id=w.work_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full work observation';
    END IF;
    fresh_work := captured.current_work;
    subscription_row := captured.current_parent;
    IF fresh_work IS DISTINCT FROM w
       OR pg_catalog.convert_to(fresh_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.kind,'UTF8')
       OR pg_catalog.convert_to(fresh_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.state,'UTF8')
       OR pg_catalog.convert_to(fresh_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(w.replay_policy,'UTF8')
       OR captured.work_id IS DISTINCT FROM w.work_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work changed under held locks';
    END IF;
    w := fresh_work;
    IF NOT is_job AND (subscription_row.subscription_id IS DISTINCT FROM w.subscription_id
       OR subscription_row.nonterminal_count IS NULL OR subscription_row.nonterminal_count<=0) THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid nonterminal parent count';
    END IF;

    IF w.ownership_revision=9223372036854775807::pg_catalog.int8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='ownership revision exhausted';
    END IF;

    final_time := pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(final_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
    END IF;

    IF w.cancellation_requested IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work cancellation requested';
    END IF;
    IF w.deadline IS NOT NULL AND final_time>=w.deadline THEN
        RAISE EXCEPTION USING ERRCODE='PZ009',MESSAGE='work deadline reached';
    END IF;
    IF final_time>=w.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='work lease expired';
    END IF;

    IF p_available_at<=final_time OR (w.deadline IS NOT NULL AND p_available_at>=w.deadline) THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid future deferral schedule';
    END IF;
    next_revision := w.ownership_revision+1;
    expected_work := w;
    expected_work.state := 'queued';
    expected_work.token := NULL;
    expected_work.lease_until := NULL;
    expected_work.ownership_revision := next_revision;
    expected_work.available_at := p_available_at;
    expected_work.updated_at := final_time;
    UPDATE modkit_events.work AS stored SET state='queued',token=NULL,lease_until=NULL,
        ownership_revision=next_revision,available_at=p_available_at,updated_at=final_time
        WHERE stored.work_id=p_work_id
        RETURNING stored.* INTO updated_work;

    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR updated_work IS DISTINCT FROM expected_work
       OR pg_catalog.convert_to(updated_work.kind,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.kind,'UTF8')
       OR pg_catalog.convert_to(updated_work.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.state,'UTF8')
       OR pg_catalog.convert_to(updated_work.replay_policy,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_work.replay_policy,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='work update postimage mismatch';
    END IF;

    INSERT INTO modkit_events.work_history AS stored
        (work_id,cycle,attempt,transition,reason,token,ownership_revision,evidence,recorded_at)
        VALUES(updated_work.work_id,updated_work.cycle,updated_work.attempt_count,
               'defer','defer',updated_work.token,updated_work.ownership_revision,''::pg_catalog.bytea,final_time)
        RETURNING stored.history_id INTO history_id_value;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid history insertion receipt';
    END IF;

    RETURN QUERY SELECT TRUE::pg_catalog.bool;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e07(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4,pg_catalog.int4,pg_catalog.timestamptz) FROM PUBLIC;

-- E30 work listing and shared job discovery indexes.
-- Source integration only; full migration and release qualification remain open.
CREATE INDEX work_namespace_created_page ON modkit_events.work (namespace,created_at,work_id);
CREATE INDEX work_jobs_created_page ON modkit_events.work (namespace,created_at,work_id)
    WHERE kind COLLATE pg_catalog."C" = 'job' COLLATE pg_catalog."C";

CREATE FUNCTION modkit_events.e30(
    p_namespace pg_catalog.bytea,
    p_after_created_at pg_catalog.timestamptz,
    p_after_work_id pg_catalog.uuid,
    p_limit pg_catalog.int4)
RETURNS TABLE(
    work_id pg_catalog.uuid, kind pg_catalog.text, subscription_id pg_catalog.bytea,
    namespace pg_catalog.bytea, command_type pg_catalog.bytea, schema_version_decimal pg_catalog.bytea,
    runnable_version pg_catalog.int4, canonical_version pg_catalog.int4, scope_evidence pg_catalog.bytea,
    scope_application pg_catalog.bytea, scope_tenant pg_catalog.bytea, scope_owner pg_catalog.bytea,
    idempotency_key pg_catalog.bytea, intent_evidence pg_catalog.bytea, semantic_input pg_catalog.bytea,
    replay_input pg_catalog.bytea, protected_binding pg_catalog.bytea, replay_policy pg_catalog.text,
    max_attempts pg_catalog.int4, deadline pg_catalog.timestamptz, original_available_at pg_catalog.timestamptz,
    state pg_catalog.text, cancellation_requested pg_catalog.bool, token pg_catalog.uuid,
    ownership_revision pg_catalog.int8, lease_until pg_catalog.timestamptz, available_at pg_catalog.timestamptz,
    cycle pg_catalog.int4, attempt_count pg_catalog.int4, dispatch_id pg_catalog.uuid, result pg_catalog.bytea,
    created_at pg_catalog.timestamptz, updated_at pg_catalog.timestamptz, success_origin pg_catalog.text,
    completion_guard_id pg_catalog.uuid, final_fence_at pg_catalog.timestamptz,
    completion_result_digest pg_catalog.bytea, resolution_operation_id pg_catalog.uuid,
    terminal_resolution_operation_id pg_catalog.uuid, resolution_present pg_catalog.bool,
    resolution_record_operation_id pg_catalog.uuid, resolution_record_operation_kind pg_catalog.text,
    resolution_record_work_id pg_catalog.uuid, resolution_record_expected_revision pg_catalog.int8,
    resolution_record_cycle pg_catalog.int4, resolution_record_attempt pg_catalog.int4,
    resolution_record_dispatch_id pg_catalog.uuid, resolution_record_outcome pg_catalog.text,
    resolution_record_retry_at pg_catalog.timestamptz, resolution_record_result pg_catalog.bytea,
    resolution_record_result_digest pg_catalog.bytea, resolution_record_reason pg_catalog.text,
    resolution_record_evidence pg_catalog.bytea, resolution_record_binding pg_catalog.bytea,
    resolution_record_resolution_root_xid pg_catalog.xid8, resolution_record_recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256
       OR (p_after_created_at IS NULL) <> (p_after_work_id IS NULL)
       OR (p_after_created_at IS NOT NULL AND modkit_events._instant_bytes(p_after_created_at) IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid work listing arguments';
    END IF;

    -- Limit indexed IDs before full integrity validation. STABLE E15 and E30
    -- share the invoking statement snapshot; no selected row is skipped.
    -- Separate branches keep the continuation tuple directly indexable.
    IF p_after_created_at IS NULL THEN
        RETURN QUERY
        WITH page AS MATERIALIZED (
            SELECT listed.work_id,listed.created_at
              FROM modkit_events.work AS listed
             WHERE listed.namespace=p_namespace
             ORDER BY listed.created_at,listed.work_id
             LIMIT p_limit
        )
        SELECT observed.*
          FROM page
          CROSS JOIN LATERAL modkit_events.e15(page.work_id) AS observed
         ORDER BY page.created_at,page.work_id;
    ELSE
        RETURN QUERY
        WITH page AS MATERIALIZED (
            SELECT listed.work_id,listed.created_at
              FROM modkit_events.work AS listed
             WHERE listed.namespace=p_namespace
               AND (listed.created_at,listed.work_id)>(p_after_created_at,p_after_work_id)
             ORDER BY listed.created_at,listed.work_id
             LIMIT p_limit
        )
        SELECT observed.*
          FROM page
          CROSS JOIN LATERAL modkit_events.e15(page.work_id) AS observed
         ORDER BY page.created_at,page.work_id;
    END IF;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e30(pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.uuid,pg_catalog.int4) FROM PUBLIC;

-- E19/E20/E21 retained audit readers. Source-only until bounded runtime QA.
-- Existing keyset indexes bound selected rows; no parent-state or commit proof.
CREATE FUNCTION modkit_events.e19(
    p_work_id pg_catalog.uuid,p_after_id pg_catalog.int8,p_limit pg_catalog.int4)
RETURNS TABLE(
    history_id pg_catalog.int8,work_id pg_catalog.uuid,cycle pg_catalog.int4,
    attempt pg_catalog.int4,transition pg_catalog.text,reason pg_catalog.text,
    token pg_catalog.uuid,ownership_revision pg_catalog.int8,evidence pg_catalog.bytea,
    recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    stored modkit_events.work_history%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_after_id IS NULL OR p_after_id<0
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid work history arguments';
    END IF;
    FOR stored IN
        SELECT listed.* FROM modkit_events.work_history AS listed
         WHERE listed.work_id=p_work_id AND listed.history_id>p_after_id
         ORDER BY listed.history_id LIMIT p_limit
    LOOP
        -- Inspect the selected page, never skip malformed rows with a filter.
        IF stored.history_id IS NULL OR stored.history_id<=0
           OR stored.work_id IS DISTINCT FROM p_work_id
           OR stored.cycle IS DISTINCT FROM 1
           OR stored.evidence IS NULL OR pg_catalog.octet_length(stored.evidence)>1048576
           OR modkit_events._instant_bytes(stored.recorded_at) IS NULL
           OR ((
               (stored.transition COLLATE pg_catalog."C" IN ('intake_runnable','intake_blocked') AND stored.attempt=0)
               OR (stored.transition COLLATE pg_catalog."C" IN ('claim','defer','recover_claim') AND stored.attempt BETWEEN 0 AND 999)
               OR (stored.transition COLLATE pg_catalog."C" IN ('failure_retry','reconcile_safe_retry') AND stored.attempt BETWEEN 1 AND 999)
               OR (stored.transition COLLATE pg_catalog."C" IN ('renew','cancel_predispatch','recover_expired_predispatch') AND stored.attempt BETWEEN 0 AND 1000)
               OR (stored.transition COLLATE pg_catalog."C" IN ('dispatch','complete','failure_terminal','failure_cancelled','cancel_running','cancel_held',
                    'recover_exhausted_predispatch','recover_dispatched','reconcile_success','reconcile_rejection','reconcile_cancelled','hold_uncertain')
                    AND stored.attempt BETWEEN 1 AND 1000)
           ) IS NOT TRUE)
           OR ((
               (stored.transition COLLATE pg_catalog."C" IN ('intake_runnable','intake_blocked') AND stored.ownership_revision=0 AND stored.token IS NULL)
               OR (stored.transition COLLATE pg_catalog."C" IN ('claim','renew','dispatch') AND stored.ownership_revision>0 AND stored.token IS NOT NULL)
               OR (stored.transition COLLATE pg_catalog."C" NOT IN ('intake_runnable','intake_blocked','claim','renew','dispatch') AND stored.ownership_revision>0 AND stored.token IS NULL)
           ) IS NOT TRUE)
           OR ((
               stored.reason COLLATE pg_catalog."C" OPERATOR(pg_catalog.~) '^[a-z][a-z0-9_]{0,255}$'
               AND (stored.transition COLLATE pg_catalog."C" IN ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain')
                   OR (stored.transition COLLATE pg_catalog."C" = 'recover_exhausted_predispatch' AND stored.reason COLLATE pg_catalog."C" = 'attempts_exhausted')
                   OR (stored.transition COLLATE pg_catalog."C" NOT IN ('failure_terminal','failure_cancelled','failure_retry','cancel_predispatch','cancel_running','cancel_held','hold_uncertain','recover_exhausted_predispatch')
                       AND stored.reason COLLATE pg_catalog."C" = stored.transition COLLATE pg_catalog."C"))
           ) IS NOT TRUE)
           OR ((stored.transition COLLATE pg_catalog."C" IN ('failure_terminal','failure_cancelled','failure_retry','reconcile_success','reconcile_rejection','reconcile_cancelled','reconcile_safe_retry','hold_uncertain')
               OR stored.evidence=''::pg_catalog.bytea) IS NOT TRUE) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid work history record';
        END IF;
        RETURN QUERY SELECT stored.history_id,stored.work_id,stored.cycle,stored.attempt,
            stored.transition,stored.reason,stored.token,stored.ownership_revision,
            stored.evidence,stored.recorded_at;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e19(pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events.e20(
    p_work_id pg_catalog.uuid,p_after_id pg_catalog.int8,p_limit pg_catalog.int4)
RETURNS TABLE(
    history_id pg_catalog.int8,work_id pg_catalog.uuid,broker_reference pg_catalog.bytea,
    transport_observation pg_catalog.bytea,recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    stored modkit_events.delivery_history%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_after_id IS NULL OR p_after_id<0
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid delivery history arguments';
    END IF;
    FOR stored IN
        SELECT listed.* FROM modkit_events.delivery_history AS listed
         WHERE listed.work_id=p_work_id AND listed.history_id>p_after_id
         ORDER BY listed.history_id LIMIT p_limit
    LOOP
        IF stored.history_id IS NULL OR stored.history_id<=0
           OR stored.work_id IS DISTINCT FROM p_work_id
           OR stored.broker_reference IS NULL
           OR pg_catalog.octet_length(stored.broker_reference)>1048576
           OR stored.transport_observation IS NULL
           OR pg_catalog.octet_length(stored.transport_observation)>1048576
           OR modkit_events._instant_bytes(stored.recorded_at) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid delivery history record';
        END IF;
        RETURN QUERY SELECT stored.history_id,stored.work_id,stored.broker_reference,
            stored.transport_observation,stored.recorded_at;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e20(pg_catalog.uuid,pg_catalog.int8,pg_catalog.int4) FROM PUBLIC;

CREATE FUNCTION modkit_events.e21(
    p_work_id pg_catalog.uuid,p_after_cycle pg_catalog.int4,p_after_attempt pg_catalog.int4,
    p_limit pg_catalog.int4)
RETURNS TABLE(
    work_id pg_catalog.uuid,cycle pg_catalog.int4,attempt pg_catalog.int4,
    dispatch_id pg_catalog.uuid,effect_id pg_catalog.bytea,request_evidence pg_catalog.bytea,
    provider_key_reference pg_catalog.bytea,dispatch_root_xid pg_catalog.xid8,
    outcome pg_catalog.text,evidence pg_catalog.bytea,recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    stored modkit_events.attempts%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_work_id IS NULL OR p_after_cycle IS NULL OR p_after_cycle<0
       OR p_after_attempt IS NULL OR p_after_attempt<0
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid attempt history arguments';
    END IF;
    FOR stored IN
        SELECT listed.* FROM modkit_events.attempts AS listed
         WHERE listed.work_id=p_work_id
           AND (listed.cycle,listed.attempt)>(p_after_cycle,p_after_attempt)
         ORDER BY listed.cycle,listed.attempt LIMIT p_limit
    LOOP
        IF stored.work_id IS DISTINCT FROM p_work_id
           OR stored.cycle IS DISTINCT FROM 1
           OR stored.attempt IS NULL OR stored.attempt NOT BETWEEN 1 AND 1000
           OR stored.dispatch_id IS NULL
           OR modkit_events._utf8_valid(stored.effect_id,256,TRUE) IS NOT TRUE
           OR stored.request_evidence IS NULL OR pg_catalog.octet_length(stored.request_evidence)>1048576
           OR (stored.provider_key_reference IS NOT NULL
               AND modkit_events._utf8_valid(stored.provider_key_reference,256,TRUE) IS NOT TRUE)
           OR stored.dispatch_root_xid IS NULL OR stored.dispatch_root_xid='0'::pg_catalog.xid8
           OR (stored.outcome COLLATE pg_catalog."C" IN
               ('dispatched','succeeded','failed','cancelled','uncertain','cancelled_unresolved','safe_retry')) IS NOT TRUE
           OR stored.evidence IS NULL OR pg_catalog.octet_length(stored.evidence)>1048576
           OR (stored.outcome COLLATE pg_catalog."C" IN ('dispatched','cancelled_unresolved')
               AND stored.evidence<>''::pg_catalog.bytea)
           OR modkit_events._instant_bytes(stored.recorded_at) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid attempt history record';
        END IF;
        RETURN QUERY SELECT stored.work_id,stored.cycle,stored.attempt,stored.dispatch_id,
            stored.effect_id,stored.request_evidence,stored.provider_key_reference,
            stored.dispatch_root_xid,stored.outcome,stored.evidence,stored.recorded_at;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e21(pg_catalog.uuid,pg_catalog.int4,pg_catalog.int4,pg_catalog.int4) FROM PUBLIC;

-- E29 retained publication history. Bounded structural observation, not delivery proof.
CREATE FUNCTION modkit_events.e29(
    p_event_id pg_catalog.bytea,p_after_id pg_catalog.int8,p_limit pg_catalog.int4)
RETURNS TABLE(
    history_id pg_catalog.int8,event_id pg_catalog.bytea,intent_id pg_catalog.uuid,
    operation_id pg_catalog.uuid,status pg_catalog.text,receipt pg_catalog.bytea,
    evidence pg_catalog.bytea,binding pg_catalog.bytea,recorded_at pg_catalog.timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    stored modkit_events.publication_history%ROWTYPE;
    identity_conflict pg_catalog.bool := FALSE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE
       OR p_after_id IS NULL OR p_after_id<0
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256 THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid publication history arguments';
    END IF;
    -- Digest discovers aliases; full IDs must not filter them out.
    FOR stored IN
        SELECT listed.* FROM modkit_events.publication_history AS listed
         WHERE listed.event_digest=pg_catalog.sha256(p_event_id) AND listed.history_id>p_after_id
         ORDER BY listed.history_id LIMIT p_limit
    LOOP
        IF stored.history_id IS NULL OR stored.history_id<=0
           OR modkit_events._utf8_valid(stored.event_id,256,TRUE) IS NOT TRUE
           OR stored.event_digest IS DISTINCT FROM pg_catalog.sha256(stored.event_id)
           OR stored.event_digest IS DISTINCT FROM pg_catalog.sha256(p_event_id)
           OR (stored.receipt IS NOT NULL AND pg_catalog.octet_length(stored.receipt)>4096)
           OR stored.evidence IS NULL OR pg_catalog.octet_length(stored.evidence)>1048576
           OR stored.binding IS NULL OR pg_catalog.octet_length(stored.binding)>1048576
           OR modkit_events._instant_bytes(stored.recorded_at) IS NULL
           OR ((
               (stored.status COLLATE pg_catalog."C" IN ('enqueue','claim_publication','recover_publication_preintent')
                   AND stored.intent_id IS NULL AND stored.operation_id IS NULL AND stored.receipt IS NULL)
               OR (stored.status COLLATE pg_catalog."C"='renew_publication'
                   AND stored.operation_id IS NULL AND stored.receipt IS NULL)
               OR (stored.status COLLATE pg_catalog."C" IN ('publication_intent','recover_publication_intent')
                   AND stored.intent_id IS NOT NULL AND stored.operation_id IS NULL AND stored.receipt IS NULL)
               OR (stored.status COLLATE pg_catalog."C" IN ('publication_confirmed','publication_rejected','publication_uncertain')
                   AND stored.intent_id IS NOT NULL AND stored.operation_id IS NULL)
               OR (stored.status COLLATE pg_catalog."C" IN ('repair_published','repair_rejected')
                   AND stored.intent_id IS NOT NULL AND stored.operation_id IS NOT NULL)
           ) IS NOT TRUE)
           OR (stored.status COLLATE pg_catalog."C" NOT IN ('repair_published','repair_rejected')
               AND stored.binding<>''::pg_catalog.bytea)
           OR (stored.status COLLATE pg_catalog."C" NOT IN
               ('publication_confirmed','publication_rejected','publication_uncertain','repair_published','repair_rejected')
               AND stored.evidence<>''::pg_catalog.bytea) THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid publication history record';
        END IF;
        IF stored.event_id IS DISTINCT FROM p_event_id THEN
            identity_conflict := TRUE;
        END IF;
        RETURN QUERY SELECT stored.history_id,stored.event_id,stored.intent_id,stored.operation_id,
            stored.status,stored.receipt,stored.evidence,stored.binding,stored.recorded_at;
    END LOOP;
    -- Check the whole selected page before reporting an otherwise coherent alias.
    -- Raising aborts this invocation; no successful partial result is exposed.
    IF identity_conflict THEN
        RAISE EXCEPTION USING ERRCODE='PZ002',MESSAGE='publication history event identity conflict';
    END IF;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e29(pg_catalog.bytea,pg_catalog.int8,pg_catalog.int4) FROM PUBLIC;

-- E22: bounded pending publication claim. E26 owns expired-lease reclamation.
CREATE FUNCTION modkit_events.e22(
    p_limit pg_catalog.int4,p_lease_seconds pg_catalog.float8,
    p_scan_after pg_catalog.bytea,p_discovery_budget pg_catalog.int4
)
RETURNS TABLE(
    record_type pg_catalog.text,visited pg_catalog.int4,next_cursor pg_catalog.bytea,pass_exhausted pg_catalog.bool,
    event_id pg_catalog.bytea,canonical_version pg_catalog.int4,
    envelope_evidence pg_catalog.bytea,replay_input pg_catalog.bytea,
    state pg_catalog.text,token pg_catalog.uuid,ownership_revision pg_catalog.int8,
    lease_until pg_catalog.timestamptz,intent_id pg_catalog.uuid,
    receipt pg_catalog.bytea,outcome_evidence pg_catalog.bytea,
    created_at pg_catalog.timestamptz,updated_at pg_catalog.timestamptz
)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    discovered pg_catalog.record;
    captured pg_catalog.record;
    locked_outbox modkit_events.outbox%ROWTYPE;
    fresh_outbox modkit_events.outbox%ROWTYPE;
    expected_outbox modkit_events.outbox%ROWTYPE;
    updated_outbox modkit_events.outbox%ROWTYPE;
    emitted_rows modkit_events.outbox[];
    emitted modkit_events.outbox%ROWTYPE;
    cursor_value pg_catalog.bytea;
    visited_count pg_catalog.int4 := 0;
    item_count pg_catalog.int4 := 0;
    exhausted_value pg_catalog.bool := FALSE;
    final_time pg_catalog.timestamptz;
    candidate_lease pg_catalog.timestamptz;
    next_revision pg_catalog.int8;
    claim_token pg_catalog.uuid;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;
    lease_wire pg_catalog.bytea;
    exponent_bits pg_catalog.int4;
    significand pg_catalog.int8;
    numerator pg_catalog.numeric;
    denominator pg_catalog.numeric;
    byte_index pg_catalog.int4;
    bit_index pg_catalog.int4;
    lease_us pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256
       OR p_discovery_budget IS NULL OR p_discovery_budget NOT BETWEEN 1 AND 4096
       OR p_discovery_budget<p_limit
       OR (p_scan_after IS NOT NULL AND pg_catalog.octet_length(p_scan_after)<>32)
       OR (p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid publication claim arguments';
    END IF;

    -- Exact ceil of the represented positive binary64 duration, not float multiplication.
    lease_wire := pg_catalog.float8send(p_lease_seconds);
    IF pg_catalog.octet_length(lease_wire)<>8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected float8 representation';
    END IF;
    exponent_bits := ((pg_catalog.get_byte(lease_wire,0)&127)<<4)|(pg_catalog.get_byte(lease_wire,1)>>4);
    IF exponent_bits <= 1002 THEN
        lease_us := 1;
    ELSE
        significand := (pg_catalog.get_byte(lease_wire,1)&15)::pg_catalog.int8;
        FOR byte_index IN 2..7 LOOP
            significand := significand*256+pg_catalog.get_byte(lease_wire,byte_index);
        END LOOP;
        significand := significand+4503599627370496;
        numerator := significand::pg_catalog.numeric * 1000000::pg_catalog.numeric;
        denominator := 1::pg_catalog.numeric;
        FOR bit_index IN 1..(1075-exponent_bits) LOOP
            denominator := denominator*2;
        END LOOP;
        lease_us := pg_catalog.div(numerator+denominator-1,denominator)::pg_catalog.int8;
    END IF;
    IF lease_us IS NULL OR lease_us<1 OR lease_us>3600000000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid quantized lease';
    END IF;

    cursor_value := p_scan_after;
    emitted_rows := ARRAY[]::modkit_events.outbox[];
    WHILE visited_count<p_discovery_budget AND item_count<p_limit LOOP
        -- Count raw identities, including ineligible and locked rows. This is
        -- cursor progress, not a certificate that every skipped row is sound.
        IF cursor_value IS NULL THEN
            SELECT listed.event_digest,listed.event_id,listed.state
              INTO discovered FROM modkit_events.outbox AS listed
              ORDER BY listed.event_digest LIMIT 1;
        ELSE
            SELECT listed.event_digest,listed.event_id,listed.state
              INTO discovered FROM modkit_events.outbox AS listed
              WHERE listed.event_digest>cursor_value
              ORDER BY listed.event_digest LIMIT 1;
        END IF;
        IF NOT FOUND THEN
            exhausted_value := TRUE;
            EXIT;
        END IF;
        IF discovered.event_digest IS NULL OR pg_catalog.octet_length(discovered.event_digest)<>32 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid discovered publication cursor';
        END IF;
        visited_count := visited_count+1;
        cursor_value := discovered.event_digest;
        IF (discovered.state COLLATE pg_catalog."C"='pending') IS NOT TRUE THEN
            CONTINUE;
        END IF;

        SELECT stored.* INTO locked_outbox FROM modkit_events.outbox AS stored
            WHERE stored.event_digest=discovered.event_digest FOR NO KEY UPDATE OF stored SKIP LOCKED;
        IF NOT FOUND THEN
            IF NOT EXISTS(SELECT 1 FROM modkit_events.outbox AS stored
                          WHERE stored.event_digest=discovered.event_digest) THEN
                RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing discovered publication';
            END IF;
            CONTINUE;
        END IF;
        -- This identifier comes from storage, not from a caller argument.
        IF modkit_events._utf8_valid(locked_outbox.event_id,256,TRUE) IS NOT TRUE
           OR locked_outbox.event_digest IS DISTINCT FROM discovered.event_digest
           OR locked_outbox.event_id IS DISTINCT FROM discovered.event_id THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='publication identity changed during acquisition';
        END IF;

        -- One fresh calling-query snapshot under the mutex. E28 supplies the
        -- complete existing integrity contract; no STABLE reader follows DML.
        WITH checked AS MATERIALIZED (
            SELECT observed.* FROM modkit_events.e28(locked_outbox.event_id) AS observed
        )
        SELECT (SELECT pg_catalog.count(*) FROM checked) AS selected_count,
               stored AS current_outbox,observed.event_id AS checked_event_id
          INTO captured
          FROM modkit_events.outbox AS stored
          LEFT JOIN checked AS observed ON TRUE
          WHERE stored.event_digest=locked_outbox.event_digest;
        IF NOT FOUND OR captured.selected_count IS DISTINCT FROM 1
           OR captured.checked_event_id IS DISTINCT FROM locked_outbox.event_id THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full publication observation';
        END IF;
        fresh_outbox := captured.current_outbox;
        IF fresh_outbox IS DISTINCT FROM locked_outbox
           OR pg_catalog.convert_to(fresh_outbox.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(locked_outbox.state,'UTF8') THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='publication changed under held lock';
        END IF;
        locked_outbox := fresh_outbox;
        IF (locked_outbox.state COLLATE pg_catalog."C"='pending') IS NOT TRUE THEN
            CONTINUE;
        END IF;
        -- As in E04, leave a successor revision instead of claiming an
        -- exhausted record. Reclamation is a separate operation.
        IF locked_outbox.ownership_revision>=9223372036854775806::pg_catalog.int8 THEN
            CONTINUE;
        END IF;
        final_time := pg_catalog.clock_timestamp();
        IF modkit_events._instant_bytes(final_time) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
        END IF;
        candidate_lease := final_time+(INTERVAL '1 microsecond' * lease_us::pg_catalog.float8);
        IF candidate_lease<=final_time OR modkit_events._instant_bytes(candidate_lease) IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid selected publication lease';
        END IF;
        next_revision := locked_outbox.ownership_revision+1;
        claim_token := pg_catalog.gen_random_uuid();
        IF claim_token IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing publication token';
        END IF;
        expected_outbox := locked_outbox;
        expected_outbox.state := 'claimed';
        expected_outbox.token := claim_token;
        expected_outbox.ownership_revision := next_revision;
        expected_outbox.lease_until := candidate_lease;
        expected_outbox.updated_at := final_time;
        UPDATE modkit_events.outbox AS stored SET state='claimed',token=claim_token,
            ownership_revision=next_revision,lease_until=candidate_lease,updated_at=final_time
            WHERE stored.event_digest=locked_outbox.event_digest
            RETURNING stored.* INTO updated_outbox;
        GET DIAGNOSTICS affected=ROW_COUNT;
        IF affected<>1 OR updated_outbox IS DISTINCT FROM expected_outbox
           OR pg_catalog.convert_to(updated_outbox.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_outbox.state,'UTF8') THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='publication update postimage mismatch';
        END IF;
        INSERT INTO modkit_events.publication_history AS stored
            (event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
            VALUES(updated_outbox.event_id,NULL,NULL,
                'claim_publication',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time)
            RETURNING stored.history_id INTO history_id_value;
        GET DIAGNOSTICS affected=ROW_COUNT;
        IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
            RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid publication history receipt';
        END IF;
        emitted_rows := pg_catalog.array_append(emitted_rows,updated_outbox);
        item_count := item_count+1;
    END LOOP;
    IF visited_count=p_discovery_budget OR item_count=p_limit THEN
        exhausted_value := FALSE;
    END IF;
    RETURN QUERY SELECT 'header'::pg_catalog.text,visited_count,cursor_value,exhausted_value,
        NULL::pg_catalog.bytea,NULL::pg_catalog.int4,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
        NULL::pg_catalog.text,NULL::pg_catalog.uuid,NULL::pg_catalog.int8,NULL::pg_catalog.timestamptz,
        NULL::pg_catalog.uuid,NULL::pg_catalog.bytea,NULL::pg_catalog.bytea,
        NULL::pg_catalog.timestamptz,NULL::pg_catalog.timestamptz;
    FOREACH emitted IN ARRAY emitted_rows LOOP
        RETURN QUERY SELECT 'item'::pg_catalog.text,NULL::pg_catalog.int4,NULL::pg_catalog.bytea,NULL::pg_catalog.bool,
            emitted.event_id,emitted.canonical_version,emitted.envelope_evidence,emitted.replay_input,
            emitted.state,emitted.token,emitted.ownership_revision,emitted.lease_until,emitted.intent_id,
            emitted.receipt,emitted.outcome_evidence,emitted.created_at,emitted.updated_at;
    END LOOP;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e22(pg_catalog.int4,pg_catalog.float8,pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;

-- E23: live exact publication renewal; E26 retains expired-lease recovery.
CREATE FUNCTION modkit_events.e23(
    p_event_id pg_catalog.bytea,p_token pg_catalog.uuid,
    p_ownership_revision pg_catalog.int8,p_lease_seconds pg_catalog.float8
)
RETURNS TABLE(lease_until pg_catalog.timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT
SET search_path = pg_catalog, pg_temp AS $body$
DECLARE
    captured pg_catalog.record;
    locked_outbox modkit_events.outbox%ROWTYPE;
    fresh_outbox modkit_events.outbox%ROWTYPE;
    expected_outbox modkit_events.outbox%ROWTYPE;
    updated_outbox modkit_events.outbox%ROWTYPE;
    final_time pg_catalog.timestamptz;
    candidate_lease pg_catalog.timestamptz;
    affected pg_catalog.int8;
    history_id_value pg_catalog.int8;
    lease_wire pg_catalog.bytea;
    exponent_bits pg_catalog.int4;
    significand pg_catalog.int8;
    numerator pg_catalog.numeric;
    denominator pg_catalog.numeric;
    byte_index pg_catalog.int4;
    bit_index pg_catalog.int4;
    lease_us pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE='PZ005',MESSAGE='unsupported transaction isolation';
    END IF;
    IF modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE
       OR p_token IS NULL OR p_ownership_revision IS NULL OR p_ownership_revision<=0
       OR (p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ006',MESSAGE='invalid publication renewal arguments';
    END IF;

    -- Exact ceil of the represented positive binary64 duration, not float multiplication.
    lease_wire := pg_catalog.float8send(p_lease_seconds);
    IF pg_catalog.octet_length(lease_wire)<>8 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='unexpected float8 representation';
    END IF;
    exponent_bits := ((pg_catalog.get_byte(lease_wire,0)&127)<<4)|(pg_catalog.get_byte(lease_wire,1)>>4);
    IF exponent_bits <= 1002 THEN
        lease_us := 1;
    ELSE
        significand := (pg_catalog.get_byte(lease_wire,1)&15)::pg_catalog.int8;
        FOR byte_index IN 2..7 LOOP
            significand := significand*256+pg_catalog.get_byte(lease_wire,byte_index);
        END LOOP;
        significand := significand+4503599627370496;
        numerator := significand::pg_catalog.numeric * 1000000::pg_catalog.numeric;
        denominator := 1::pg_catalog.numeric;
        FOR bit_index IN 1..(1075-exponent_bits) LOOP
            denominator := denominator*2;
        END LOOP;
        lease_us := pg_catalog.div(numerator+denominator-1,denominator)::pg_catalog.int8;
    END IF;
    IF lease_us IS NULL OR lease_us<1 OR lease_us>3600000000 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid quantized lease';
    END IF;

    -- Digest discovery does not hide a different-full-ID alias from E28.
    PERFORM stored.event_digest FROM modkit_events.outbox AS stored
        WHERE stored.event_digest=pg_catalog.sha256(p_event_id) FOR NO KEY UPDATE OF stored;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale publication fence';
    END IF;
    -- New command snapshot after a potentially blocking lock acquisition.
    SELECT stored.* INTO locked_outbox FROM modkit_events.outbox AS stored
        WHERE stored.event_digest=pg_catalog.sha256(p_event_id);
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale publication fence';
    END IF;
    IF locked_outbox.token IS DISTINCT FROM p_token
       OR locked_outbox.ownership_revision IS DISTINCT FROM p_ownership_revision THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='stale publication fence';
    END IF;
    IF (locked_outbox.state COLLATE pg_catalog."C" IN ('claimed','publishing')) IS NOT TRUE THEN
        RAISE EXCEPTION USING ERRCODE='PZ004',MESSAGE='invalid publication state';
    END IF;

    -- One complete preimage validator under the mutex, before any write.
    WITH checked AS MATERIALIZED (
        SELECT observed.* FROM modkit_events.e28(p_event_id) AS observed
    )
    SELECT (SELECT pg_catalog.count(*) FROM checked) AS selected_count,
           stored AS current_outbox,observed.event_id AS checked_event_id
      INTO captured
      FROM modkit_events.outbox AS stored
      LEFT JOIN checked AS observed ON TRUE
      WHERE stored.event_digest=locked_outbox.event_digest;
    IF NOT FOUND OR captured.selected_count IS DISTINCT FROM 1
       OR captured.checked_event_id IS DISTINCT FROM p_event_id THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='missing full publication observation';
    END IF;
    fresh_outbox := captured.current_outbox;
    IF fresh_outbox IS DISTINCT FROM locked_outbox
       OR pg_catalog.convert_to(fresh_outbox.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(locked_outbox.state,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='publication changed under held lock';
    END IF;
    locked_outbox := fresh_outbox;
    final_time := pg_catalog.clock_timestamp();
    IF modkit_events._instant_bytes(final_time) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid final database time';
    END IF;
    IF final_time>=locked_outbox.lease_until THEN
        RAISE EXCEPTION USING ERRCODE='PZ003',MESSAGE='publication lease expired';
    END IF;
    candidate_lease := final_time+(INTERVAL '1 microsecond' * lease_us::pg_catalog.float8);
    IF modkit_events._instant_bytes(candidate_lease) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='lease timestamp outside supported domain';
    END IF;
    IF candidate_lease<locked_outbox.lease_until THEN
        candidate_lease := locked_outbox.lease_until;
    END IF;
    IF candidate_lease<=final_time OR modkit_events._instant_bytes(candidate_lease) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid renewed publication lease';
    END IF;
    expected_outbox := locked_outbox;
    expected_outbox.lease_until := candidate_lease;
    expected_outbox.updated_at := final_time;
    UPDATE modkit_events.outbox AS stored SET lease_until=candidate_lease,updated_at=final_time
        WHERE stored.event_digest=locked_outbox.event_digest
        RETURNING stored.* INTO updated_outbox;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 OR updated_outbox IS DISTINCT FROM expected_outbox
       OR pg_catalog.convert_to(updated_outbox.state,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(expected_outbox.state,'UTF8') THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='publication update postimage mismatch';
    END IF;
    INSERT INTO modkit_events.publication_history AS stored
        (event_id,intent_id,operation_id,status,receipt,evidence,binding,recorded_at)
        VALUES(updated_outbox.event_id,updated_outbox.intent_id,NULL,
            'renew_publication',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time)
        RETURNING stored.history_id INTO history_id_value;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 OR history_id_value IS NULL OR history_id_value<=0 THEN
        RAISE EXCEPTION USING ERRCODE='PZ012',MESSAGE='invalid publication history receipt';
    END IF;
    RETURN QUERY SELECT updated_outbox.lease_until;
END
$body$;
REVOKE ALL ON FUNCTION modkit_events.e23(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.float8) FROM PUBLIC;
