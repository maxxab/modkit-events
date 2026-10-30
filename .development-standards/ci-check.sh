#!/bin/sh
# CI must fetch complete history and supply the reviewed base/head commit IDs.
set -eu
: "${BASE:?Set BASE to the reviewed base commit}"
: "${HEAD:?Set HEAD to the reviewed head commit}"
BASE=$(git merge-base "$BASE" "$HEAD")
exec python3 .development-standards/standards.py check --base "$BASE" --head "$HEAD"
