#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
OUT="$REPO/build"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "=== Building APWorld ==="
"$REPO/build_ap.sh"

echo "=== Building OpenOMF ==="
"$REPO/build.sh"

echo "=== Building OpenOMF (Windows) ==="
"$REPO/build-windows.sh"

echo "=== Assembling $OUT ==="
cp "$REPO/omf/build/openomf"    "$OUT/"
cp -rL "$REPO/omf/build/lib"       "$OUT/"
cp -rL "$REPO/omf/build/resources" "$OUT/"
cp -rL "$REPO/omf/build/shaders"   "$OUT/"
cp "$REPO/bin/openomf.apworld" "$OUT/"

# Remove libs that conflict with system gtk4/glib (zenity and other system tools
# inherit LD_LIBRARY_PATH and choke on older bundled versions of these).
rm -f "$OUT/lib/libpcre2-8.so"* "$OUT/lib/libpng16.so"*

cat > "$OUT/run.sh" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
exec env LD_LIBRARY_PATH="$DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$DIR/openomf" "$@"
EOF
chmod +x "$OUT/run.sh"

echo "Done. Run with: $OUT/run.sh"

echo "=== Packaging ==="
VERSION="$(git -C "$REPO" describe --tags --always 2>/dev/null || echo "dev")"
BUILDS="$REPO/builds"
mkdir -p "$BUILDS"

# Linux zip
(cd "$OUT" && zip -r "$BUILDS/openomf-linux.$VERSION.zip" .)

# Windows zip
WIN="$REPO/omf/build-windows"
(cd "$WIN" && zip -r "$BUILDS/openomf-windows.$VERSION.zip" .)

echo "Packages:"
ls -lh "$BUILDS/openomf-"*".$VERSION.zip"
