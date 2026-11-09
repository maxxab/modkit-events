# Opaque evidence alignment vectors

SQL NOT_RUN. FL10 supervisor confirmed ordinary E01 manifest/E03 broker_reference/E06 request_evidence use0..1048576 bytes. Test each with exact empty BYTEA, one NUL byte, exactly1048576 bytes and1048577 bytes. First three pass standalone field validation; max+1 rejects PZ006 at public boundary. Empty bytes must not become NULL or a fabricated receipt. Other admission/capacity/fence requirements still apply and must use valid fixture values.

Receipt is separate explicit0..4096: test empty,4096 and4097. The receipt ceiling must not be applied to broker reference, manifest or dispatch evidence. Structured semantic/envelope/intent inputs remain subject to their exact grammar and cannot be empty simply because the generic byte ceiling permits zero. No SQL security prerequisite requiring nonempty ordinary opaque evidence has been found; do not invent one silently.
