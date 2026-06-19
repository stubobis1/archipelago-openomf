#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"
bash build.sh
"${SCRIPT_DIR}/omf/build/run.sh"
