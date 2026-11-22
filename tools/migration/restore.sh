#!/bin/sh
# SF6 restore (Issue #32)
set -eu
cd "$(dirname "$0")/../.."
exec python3 tools/migration/restore.py "$@"
