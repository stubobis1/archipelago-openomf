#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Resolve AP save directory using the same priority as the game:
# 1. $OPENOMF_STATE_PATH, 2. $XDG_STATE_HOME, 3. SDL pref path fallback
if [ -n "$OPENOMF_STATE_PATH" ]; then
    STATE_DIR="$OPENOMF_STATE_PATH"
elif [ -n "$XDG_STATE_HOME" ]; then
    STATE_DIR="$XDG_STATE_HOME/OpenOMF"
else
    STATE_DIR="${HOME}/.local/share/OpenOMF"
fi

AP_SAVE_DIR="${STATE_DIR}/save/ap"

echo "Wiping AP saves: ${AP_SAVE_DIR}"
rm -rf "${AP_SAVE_DIR}"

cd "$SCRIPT_DIR"
bash build.sh
"${SCRIPT_DIR}/omf/build/run.sh"
