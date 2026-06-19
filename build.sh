#!/bin/bash
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
IMAGE="openomf-build"
BUILD="$REPO/omf/build"

docker build -t "$IMAGE" -f "$REPO/omf/Dockerfile.build" "$REPO/omf"

docker run --rm -v "$REPO/omf:/src" "$IMAGE" bash -c "
  git config --global --add safe.directory /src
  rm -rf /src/build
  mkdir /src/build
  cd /src/build
  cmake -DCMAKE_BUILD_TYPE=Debug -DUSE_ARCHIPELAGO=ON ..
  make -j\$(nproc)
  chown -R $(id -u):$(id -g) /src/build
"

# Bundle shared libs (exclude glibc — must use host's)
mkdir -p "$BUILD/lib"
docker run --rm -v "$BUILD:/out" "$IMAGE" bash -c "
  ldd /out/openomf | grep '=>' | awk '{print \$3}' | grep -v '^\$' | while read lib; do
    cp \"\$lib\" /out/lib/ 2>/dev/null || true
  done
  cp /usr/lib/x86_64-linux-gnu/pulseaudio/libpulsecommon-16.1.so /out/lib/ 2>/dev/null || true
  chown -R $(id -u):$(id -g) /out/lib
"
rm -f "$BUILD/lib/libc.so.6" "$BUILD/lib/libm.so.6" "$BUILD/lib/libmvec.so.1" "$BUILD/lib/libdl.so.2"
rm -f "$BUILD/lib/libssl.so"* "$BUILD/lib/libcrypto.so"*
rm -f "$BUILD/lib/libglib-2.0.so"* "$BUILD/lib/libgmodule-2.0.so"* "$BUILD/lib/libgobject-2.0.so"*

# Game data: symlink OMF2097 files into resources/
# Try XDG_DATA_HOME first, fall back to the standard ~/.local/share location.
OMF2097="${XDG_DATA_HOME:-$HOME/.local/share}/OpenOMF/OMF2097"
[ -d "$OMF2097" ] || OMF2097="$HOME/.local/share/OpenOMF/OMF2097"
if [ -d "$OMF2097" ]; then
  for f in "$OMF2097"/*; do
    base="$(basename "$f")"
    target="$BUILD/resources/$base"
    [ -e "$target" ] || ln -s "$f" "$target"
  done
else
  echo "WARNING: OMF2097 game data not found at $OMF2097"
fi

# Write launcher if missing
if [ ! -f "$BUILD/run.sh" ]; then
  cat > "$BUILD/run.sh" <<'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec env LD_LIBRARY_PATH="$DIR/lib:$LD_LIBRARY_PATH" "$DIR/openomf" "$@"
EOF
  chmod +x "$BUILD/run.sh"
fi

echo "Done. Run with: $BUILD/run.sh"
