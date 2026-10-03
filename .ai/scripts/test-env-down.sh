#!/bin/sh
# om-prepare-test-env: generated entrypoint (contract v2)
# history: 2026-10-03 stop only services authenticated by the private product supervisor.
set -eu
LAYA_QA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
LAYA_QA_PYTHON=$(uv python find --offline 3.12)
exec "$LAYA_QA_PYTHON" "$LAYA_QA_ROOT/scripts/test_environment.py" down "$@"
