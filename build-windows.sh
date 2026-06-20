#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
OMF="$REPO/omf"
IMAGE="openomf-build-windows"

docker build -t "$IMAGE" -f "$OMF/Dockerfile.build-windows" "$OMF"
docker build -t openomf-build -f "$OMF/Dockerfile.build" "$OMF"

# Generate language files using Linux build image (has SDL2 etc.)
docker run --rm -v "$REPO:/repo" openomf-build bash -c "
  git config --global --add safe.directory '*'
  cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_TOOLS=ON \
    -DUSE_ARCHIPELAGO=ON \
    -DBUILD_LANGUAGES=ON \
    -DUSE_MINIUPNPC=OFF \
    -DUSE_NATPMP=OFF \
    -S /repo/omf -B /repo/omf/build-langtools
  cmake --build /repo/omf/build-langtools --target build_languages -j\$(nproc)
  chown -R $(id -u):$(id -g) /repo/omf/build-langtools
"

docker run --rm -v "$REPO:/repo" "$IMAGE" bash -c "
  set -euo pipefail

  # Pre-built Windows deps (mirrors upstream CI)
  wget -q https://github.com/omf2097/openomf-win-build/archive/refs/heads/main.zip -O /tmp/win-build.zip
  unzip -q /tmp/win-build.zip -d /tmp
  mv /tmp/openomf-win-build-main /win-build

  # OpenSSL for mingw64 from MSYS2 (needed for AP wss:// support)
  MSYS2_BASE=https://repo.msys2.org/mingw/mingw64
  SSL_PKG=\$(wget -qO- \"\$MSYS2_BASE/\" | grep -oP 'mingw-w64-x86_64-openssl-[\d.]+-\d+-any\.pkg\.tar\.zst' | sort -V | tail -1)
  wget -q \"\$MSYS2_BASE/\$SSL_PKG\" -O /tmp/openssl.pkg.tar.zst
  mkdir -p /tmp/openssl-pkg
  tar -xf /tmp/openssl.pkg.tar.zst -C /tmp/openssl-pkg
  cp -r /tmp/openssl-pkg/mingw64/include/* /win-build/include/ 2>/dev/null || true
  cp -r /tmp/openssl-pkg/mingw64/lib/*     /win-build/lib/     2>/dev/null || true

  # asio is header-only — copy system headers (1.28.x, compatible with websocketpp)
  cp /usr/include/asio.hpp /win-build/include/
  cp -r /usr/include/asio  /win-build/include/

  git config --global --add safe.directory '*'
  rm -rf /repo/omf/build-windows
  mkdir /repo/omf/build-windows

  cmake \
    -DCMAKE_BUILD_TYPE=Release \
    --toolchain /repo/omf/cmake-scripts/mingw-w64-toolchain.cmake \
    -DCMAKE_PREFIX_PATH=/win-build \
    -DCMAKE_INCLUDE_PATH=/win-build/include \
    -DCMAKE_LIBRARY_PATH=/win-build/lib \
    -DCMAKE_FIND_ROOT_PATH=/win-build \
    -DUSE_ARCHIPELAGO=ON \
    -DBUILD_LANGUAGES=OFF \
    -S /repo/omf -B /repo/omf/build-windows

  cmake --build /repo/omf/build-windows -j\$(nproc)

  # Copy generated language files into Windows build resources
  cp /repo/omf/build-langtools/resources/*.DAT2 /repo/omf/build-windows/resources/ 2>/dev/null || true
  cp /repo/omf/build-langtools/resources/*.LNG  /repo/omf/build-windows/resources/ 2>/dev/null || true
  cp /repo/omf/build-langtools/resources/*.LNG2 /repo/omf/build-windows/resources/ 2>/dev/null || true

  # Bundle DLLs next to exe
  cp /win-build/bin/*.dll /repo/omf/build-windows/
  # OpenSSL DLLs from MSYS2 package
  cp /tmp/openssl-pkg/mingw64/bin/libssl-*.dll    /repo/omf/build-windows/ 2>/dev/null || true
  cp /tmp/openssl-pkg/mingw64/bin/libcrypto-*.dll /repo/omf/build-windows/ 2>/dev/null || true
  # MinGW runtime DLLs (C++ stdlib, GCC SEH runtime)
  MINGW_RT=\$(find /usr/lib/gcc/x86_64-w64-mingw32 -maxdepth 1 -name '*-win32' -type d | head -1)
  cp \$MINGW_RT/libstdc++-6.dll    /repo/omf/build-windows/
  cp \$MINGW_RT/libgcc_s_seh-1.dll /repo/omf/build-windows/ 2>/dev/null || true

  chown -R $(id -u):$(id -g) /repo/omf/build-windows
"

# Copy OMF2097 game data into resources/
OMF2097="${XDG_DATA_HOME:-$HOME/.local/share}/OpenOMF/OMF2097"
if [ -d "$OMF2097" ]; then
    cp "$OMF2097"/* "$OMF/build-windows/resources/"
    echo "Game data copied from $OMF2097"
else
    echo "WARNING: OMF2097 data not found at $OMF2097 — copy manually"
fi

echo "Build complete: $OMF/build-windows/openomf.exe"
