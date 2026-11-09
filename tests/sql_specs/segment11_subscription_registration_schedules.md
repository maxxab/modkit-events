# E01→E18 qualification schedules

DESIGN/FIXTURE ONLY, NOT_RUN/not parsed. Current contract proposal and exactsetuptrace: external foundation/e01-v2/design.md and manual-trace.md. Existing SQL/readers/fixtures/setup/docs frozen. No E01body yet.

SingleDO prospectively covers firstregistration strictUnit/following E18, exact immutable repeats preserving time/count (includingfullcapacity), opaqueempty/nonUTF8/1MiBmanifest, NULID/256byteUnicodegroup/MAXint4capacity, fullmanifest/group/capacityPZ002, reachable existinginfinitytimePZ012 beforeconflict, invalidinputPZ006/nativeint4overflow22003, expectedonlynewparent delta and final15relation equality. Everysetupseed source-traced through all actual table/trigger/FK/generated rules. No malformedboundedcount or hidden constraint bypass. SingleDO cannot prove concurrency/callercommit/effectiveACL.

Required independent2session schedules after actualbody/source acceptance:

- Same-ID/sameimmutable: A inserts helduncommitted, B beginsREADCOMMITTED and actuallyblocks on uniqueidentity; releaseA COMMIT deterministically after observedblockedcommand, B normalTrue/freshparent withAretainedtimestamp/count. Oneparentonly.
- Same-ID/differingmanifest/group/capacity: same barrier, B getsPZ002 afterAcommit and nooverwrite. Capture loserroot/statementrollback and completefootprints independently.
- Aabort: blockB atuniqueness then AROLLBACK, B mayinsert/returnTrue, eventualoneparent withitsown supportedtime; callerconfirmscommit separately.
- Existingparent countmutex: A owns parentNOKEYUPDATE, performs a separatelyreviewed lawfulcount mutation/producer; B same E01blocked, then rereads supported currentcount andpreserves it, notzeroreset/stalesnapshot. Untilproducer exists ownerstructuralcount setup is bounded and explicitlynotpublic provenance.
- Callerrollback: separate released root demonstrates E01True followed bycallerROLLBACK leavesno registration; True nevermeansCOMMIT. Parent-before-work order source/actualcomposedproducer proof awaitsE03; nohiddenroot/retryauthority.

No sleeps as synchronization or claims from taskqueued/sessionidle alone. Each schedule needs approved commands/barriers/independentoracles/logs/cleanup/currentpins and rootservicelease first. Physicalplans/indexuse, isolation/nativecoercion matrix, installedowner/defaultACL/membership/temp/overload/denials, all84/3recipes/artifacts/platform/application/migration remainowed. Realhashcollision is irrelevant to full-byte E01PK; nohashoverride.

Meaningful NEW missingE01RED requires rootreviewedsetup then exact42883afterchosenmarker and clean independentaftermath. OldreaderRED/GREEN are not E01proof. ProposedRED neverreadsS11. No sourcebody/GRANT/helper/type/catalog/decoder/schema-docchange authorized. Fresh userconfirmationmandatory before PyPI/tagtrigger.
