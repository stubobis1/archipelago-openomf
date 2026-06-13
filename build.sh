#!/bin/bash
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
IMAGE="openomf-build"
BUILD="$REPO/build"

docker build -t "$IMAGE" -f "$REPO/Dockerfile.build" "$REPO"

docker run --rm -v "$REPO:/src" "$IMAGE" bash -c "
  git config --global --add safe.directory /src
  rm -rf /src/build
  mkdir /src/build
  cd /src/build
  cmake -DCMAKE_BUILD_TYPE=Debug ..
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

# Game data: move OMF2097 files into resources/ if not already there
if [ -f "$BUILD/SOUNDS.DAT" ]; then
  mv "$BUILD"/*.DAT "$BUILD"/*.BK "$BUILD"/*.PSM "$BUILD"/*.PIC "$BUILD"/*.TRN "$BUILD"/*.PCX "$BUILD"/*.AF "$BUILD/resources/" 2>/dev/null || true
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
