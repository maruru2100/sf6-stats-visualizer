#!/bin/sh
# SF6 backup / migration export (Issue #32)
set -eu
cd "$(dirname "$0")/../.."
exec python3 tools/migration/backup.py "$@"
