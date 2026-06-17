#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AP_DIR="$SCRIPT_DIR/archipelago"

# Generate SVGs from PlantUML files via kroki.io (vector = crisp at any size)
for puml in "$SCRIPT_DIR"/*.puml; do
    [ -f "$puml" ] || continue
    svg="${puml%.puml}.svg"
    # Inject layout hints: wrap long strings, force each HAR onto its own row
    src=$(python3 - "$puml" <<'PYEOF'
import sys
hars = ['Jaguar','Shadow','Thorn','Pyros','Electra','Katana','Shredder','Flail','Gargoyle','Chronos','Nova']
with open(sys.argv[1]) as f:
    content = f.read()
content = content.replace('@startuml\n', '@startuml\nskinparam wrapWidth 200\n', 1)
hidden = '\n'.join(f'"{h} Mechlab" -[hidden]down-> "{hars[i+1]} Mechlab"' for i, h in enumerate(hars[:-1]))
content = content.replace('@enduml', hidden + '\n@enduml', 1)
print(content, end='')
PYEOF
)
    http_code=$(curl -s -o "$svg" -w "%{http_code}" \
        -X POST https://kroki.io/plantuml/svg \
        -H "Content-Type: application/json" \
        --data-binary "{\"diagram_source\": $(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$src")}")
    if [ "$http_code" = "200" ]; then
        echo "Generated $(basename "$svg")"
    else
        echo "WARNING: kroki.io returned $http_code for $(basename "$puml")" >&2
    fi
done

if [ -f "$SCRIPT_DIR/.python-version" ]; then
    PY_VER="$(cat "$SCRIPT_DIR/.python-version")"
    PYENV_PY="$HOME/.pyenv/versions/$PY_VER/bin/python3"
    [ -x "$PYENV_PY" ] && PYTHON3="$PYENV_PY" || PYTHON3="python3"
else
    PYTHON3="python3"
fi

SLOT="${1:-player}"
PASSWORD="${2:-}"
PORT="${3:-38281}"
PLAYERS_DIR="/tmp/omf_players"
OUT_DIR="/tmp/omf_output"

mkdir -p "$PLAYERS_DIR" "$OUT_DIR"

# 1. Generate template YAML
cat > "$PLAYERS_DIR/${SLOT}.yaml" << YAML
name: ${SLOT}
game: "One Must Fall: 2097"

"One Must Fall: 2097":
  goal_tournament: world_championship
  starting_har: random_selection
  har_stat_max: 9
  pilot_stat_max: 25
  include_buy_locations: true
  buy_cost_factor: 100
YAML

# 2. Generate multiworld (remove stale output first)
rm -f "$OUT_DIR"/AP_*.zip
PYTHONPATH="$AP_DIR" "$PYTHON3" "$AP_DIR/Generate.py" \
    --player_files_path "$PLAYERS_DIR" \
    --outputpath "$OUT_DIR"

# Find the output zip
MULTIDATA=$(find "$OUT_DIR" -name "AP_*.zip" | sort | tail -1)
if [ ! -f "$MULTIDATA" ]; then
    echo "ERROR: no AP_*.zip found in $OUT_DIR" >&2
    exit 1
fi

# 3. Host multiworld
PASS_ARGS=()
[ -n "$PASSWORD" ] && PASS_ARGS=(--password "$PASSWORD")

echo "Hosting $MULTIDATA on port $PORT..."
PYTHONPATH="$AP_DIR" "$PYTHON3" "$AP_DIR/MultiServer.py" \
    "$MULTIDATA" \
    --port "$PORT" \
    "${PASS_ARGS[@]}"
