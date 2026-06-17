#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
AP_DIR="$REPO/archipelago"
OUT_DIR="$REPO/bin"

mkdir -p "$OUT_DIR"

cd "$AP_DIR"
/home/stubob/.pyenv/versions/3.13.13/bin/python3 Launcher.py "Build APWorlds" "One Must Fall: 2097"

cp "$AP_DIR/build/apworlds/openomf.apworld" "$OUT_DIR/"
echo "Copied $OUT_DIR/openomf.apworld"
