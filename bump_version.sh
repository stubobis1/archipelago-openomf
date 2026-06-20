#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
JSON="$REPO/archipelago/worlds/openomf/archipelago.json"

current="$(git -C "$REPO" describe --tags --abbrev=0 2>/dev/null || echo "none")"
echo "Current version: $current"

read -rp "New version (semver, e.g. 1.2.3): " version

if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: '$version' is not valid semver (X.Y.Z)" >&2
    exit 1
fi

if git -C "$REPO" rev-parse "$version" &>/dev/null; then
    echo "Error: tag '$version' already exists in root repo" >&2
    exit 1
fi

echo "Updating $JSON ..."
tmp="$(mktemp)"
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
d['world_version'] = sys.argv[2]
with open(sys.argv[1], 'w') as f:
    json.dump(d, f, indent='\t')
    f.write('\n')
" "$JSON" "$version"

echo "Tagging omf subrepo ..."
git -C "$REPO/omf" tag "$version"

echo "Tagging root repo ..."
git -C "$REPO" tag "$version"

echo "Done. Version bumped to $version"
echo "  archipelago.json world_version updated"
echo "  omf tagged: $version"
echo "  root tagged: $version"
echo ""
echo "Push tags when ready:"
echo "  git -C omf push origin $version"
echo "  git push origin $version"
