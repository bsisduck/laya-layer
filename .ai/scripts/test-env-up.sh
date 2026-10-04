#!/bin/sh
# om-prepare-test-env: generated entrypoint (contract v2)
# regenerate with: om-prepare-test-env --regenerate
# history: 2026-10-04 accept explicit local-console selection; probe bootstrap without reading credentials.
# history: 2026-10-03 use the product launcher/cache/ownership and a private QA installation.
set -eu
LAYA_QA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
LAYA_QA_PYTHON=$(uv python find --offline 3.12)
exec "$LAYA_QA_PYTHON" "$LAYA_QA_ROOT/scripts/test_environment.py" up "$@"
