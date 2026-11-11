-- Source vectors authored before J helpers. NOT RUN, no execution authorization.
DO $test$
BEGIN
    IF modkit_events._decimal_valid(pg_catalog.decode('32313437343833363438','hex'),FALSE) IS DISTINCT FROM TRUE
       OR modkit_events._decimal_valid(pg_catalog.decode('3031','hex'),FALSE) IS DISTINCT FROM FALSE
       OR modkit_events._decimal_valid(pg_catalog.decode('2d30','hex'),TRUE) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'decimal canonical grammar violation';
    END IF;
    IF modkit_events._float_hex_valid(pg_catalog.decode('3078302e30702b30','hex')) IS DISTINCT FROM TRUE
       OR modkit_events._float_hex_valid(pg_catalog.decode('2d3078302e30702b30','hex')) IS DISTINCT FROM TRUE
       OR modkit_events._float_hex_valid(pg_catalog.decode('3078312e30303030303030303030303030702d30','hex')) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'signed zero/exponent canonical grammar violation';
    END IF;
    IF modkit_events._j_nodes(pg_catalog.decode('6e','hex'),0,262144) IS DISTINCT FROM 1
       OR modkit_events._j_nodes(pg_catalog.decode('6100000000','hex'),32,262144) IS DISTINCT FROM 1
       OR modkit_events._j_nodes(pg_catalog.decode('610000000100000000000000016e','hex'),32,262144) IS NOT NULL THEN
        RAISE EXCEPTION 'J root/leaf depth violation';
    END IF;
    IF modkit_events._j_nodes(pg_catalog.decode('73000000000000000100','hex'),0,262144) IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'J NUL string rejected';
    END IF;
    IF modkit_events._j_nodes(pg_catalog.decode('6900000000000000023031','hex'),0,262144) IS NOT NULL THEN
        RAISE EXCEPTION 'J noncanonical integer accepted';
    END IF;
END
$test$;
