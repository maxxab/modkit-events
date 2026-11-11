-- Authored before exact-rational decimal helper. NOT_RUN: SQL execution denied.
DO $test$
DECLARE
    input pg_catalog.text;
    expected pg_catalog.text;
    pair pg_catalog.text[];
BEGIN
    FOREACH pair SLICE 1 IN ARRAY ARRAY[
        ARRAY['0.1','0x1.999999999999ap-4'],
        ARRAY['-0.0','-0x0.0p+0'],
        ARRAY['5e-324','0x0.0000000000001p-1022'],
        ARRAY['2.4703282292062327e-324','0x0.0p+0'],
        ARRAY['2.4703282292062328e-324','0x0.0000000000001p-1022'],
        ARRAY['9007199254740993.0','0x1.0000000000000p+53'],
        ARRAY['9007199254740995.0','0x1.0000000000002p+53'],
        ARRAY['1.7976931348623157e308','0x1.fffffffffffffp+1023'],
        ARRAY['1e-999999','0x0.0p+0']
    ] LOOP
        input := pair[1]; expected := pair[2];
        IF modkit_events._decimal_float_hex(pg_catalog.convert_to(input,'UTF8')) IS DISTINCT FROM pg_catalog.convert_to(expected,'UTF8') THEN
            RAISE EXCEPTION 'binary64 known answer differs';
        END IF;
    END LOOP;
    FOREACH input IN ARRAY ARRAY['1.7976931348623159e308','1e999999','01.0','1e','1e0000000','NaN','1'] LOOP
        IF modkit_events._decimal_float_hex(pg_catalog.convert_to(input,'UTF8')) IS NOT NULL THEN
            RAISE EXCEPTION 'invalid/nonfloat/overflow token accepted';
        END IF;
    END LOOP;
END
$test$;
