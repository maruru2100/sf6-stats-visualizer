#!/bin/sh
# SF6 merge / differential insert (Issue #44)
set -eu
cd "$(dirname "$0")/../.."
exec python3 tools/migration/merge.py "$@"
