#!/bin/sh
# Launch the app straight from source, for a quick manual check before
# running scripts/build_mac.sh. No packaging step, so it starts in
# seconds and picks up source changes on the next run with no rebuild.
set -eu
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python3 ]; then
    echo "No .venv/ found. Run scripts/setup_mac.sh first." >&2
    exit 1
fi

.venv/bin/python3 run_viewer.pyw "$@"
