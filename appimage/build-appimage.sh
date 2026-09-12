#!/usr/bin/env bash
# Build Buzz as a Linux AppImage.
#
# Prerequisites — install before running:
#   Ubuntu/Debian:
#     sudo apt install ffmpeg libportaudio2 libpulse0 libvulkan-dev ccache cmake \
#       libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
#       libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 \
#       libxcb-cursor0 libgl1-mesa-dev gettext
#   RHEL/AlmaLinux 9:
#     sudo dnf install epel-release
#     sudo dnf install ffmpeg-free portaudio pulseaudio-libs-devel vulkan-loader-devel \
#       ccache cmake libxkbcommon-x11 libxcb mesa-libGL-devel gettext
#
#   Both: uv, Vulkan SDK (https://vulkan.lunarg.com/sdk/home)
#
# Usage:
#   ./appimage/build-appimage.sh          # standalone
#   uv run make bundle_appimage           # via Makefile

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build/appimage"
APPDIR="$BUILD_DIR/Buzz.AppDir"
ARCH="$(uname -m)"
VERSION="$(grep '^version := ' "$PROJECT_DIR/Makefile" | head -1 | awk '{print $3}')"
OUTPUT="$PROJECT_DIR/dist/Buzz-${VERSION}-${ARCH}.AppImage"

echo "==> Building Buzz ${VERSION} AppImage for ${ARCH}"

# ── Step 1: PyInstaller bundle ──────────────────────────────────────────────
# Reuses the existing Buzz.spec (same as macOS/Windows builds).
# Produces dist/Buzz/ with the self-contained application.
if [ ! -d "$PROJECT_DIR/dist/Buzz" ]; then
    echo "==> Running PyInstaller..."
    cd "$PROJECT_DIR"
    uv run make dist/Buzz
fi

# ── Step 2: Create AppDir ───────────────────────────────────────────────────
echo "==> Assembling AppDir..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
         "$APPDIR/usr/share/metainfo"

# Copy entire PyInstaller output into usr/bin/
cp -a "$PROJECT_DIR/dist/Buzz/." "$APPDIR/usr/bin/"

# Strip the executable-stack flag from bundled shared objects. uv's
# python-build-standalone marks libpython PT_GNU_STACK=RWE, and kernels from
# Linux 7.0 (Ubuntu 26.04) on refuse that at dlopen time, so the app dies with
# "cannot enable executable stack as shared object requires: Invalid argument".
# Patch the AppDir copy, never the shared uv Python cache.
echo "==> Clearing executable-stack flags..."
uv run --no-project "$SCRIPT_DIR/clear-execstack.py" "$APPDIR/usr/bin"

# Bundle uv: the in-app CUDA installer needs it to build the private CUDA venv.
# The AppImage ships no standalone interpreter, and the host's python3 is
# whatever the distro installed — on Ubuntu 26.04 that is 3.14, which has no
# torch wheels. uv downloads a CPython matching the one Buzz is frozen with.
echo "==> Bundling uv..."
UV_BIN="$(command -v uv)"
if [ -z "$UV_BIN" ]; then
    echo "ERROR: uv not found in PATH; it is required for in-app CUDA installation." >&2
    exit 1
fi
cp "$(readlink -f "$UV_BIN")" "$APPDIR/usr/bin/uv"
chmod +x "$APPDIR/usr/bin/uv"

# ── Step 3: Desktop integration ─────────────────────────────────────────────
# Desktop file — Exec must be just the binary name for AppImage spec
cat > "$APPDIR/Buzz.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Buzz
GenericName=Audio Transcriber
Comment=Transcribe and translate audio offline
Exec=Buzz
Icon=Buzz
Terminal=false
Categories=AudioVideo;Audio;
MimeType=audio/mpeg;audio/wav;audio/ogg;audio/flac;video/mp4;video/webm;
EOF
cp "$APPDIR/Buzz.desktop" "$APPDIR/usr/share/applications/"

# Icon (SVG at AppDir root + XDG hicolor location)
cp "$PROJECT_DIR/share/icons/io.github.chidiwilliams.Buzz.svg" "$APPDIR/Buzz.svg"
cp "$PROJECT_DIR/share/icons/io.github.chidiwilliams.Buzz.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/Buzz.svg"

# AppStream metainfo (appimagetool expects .appdata.xml suffix)
cp "$PROJECT_DIR/share/metainfo/io.github.chidiwilliams.Buzz.metainfo.xml" \
   "$APPDIR/usr/share/metainfo/io.github.chidiwilliams.Buzz.appdata.xml"
APPSTREAM_FILE="$APPDIR/usr/share/metainfo/io.github.chidiwilliams.Buzz.appdata.xml"

# ── Step 4: AppRun entry point ──────────────────────────────────────────────
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
SELF="$(readlink -f "$0")"
APPDIR="$(dirname "$SELF")"

export PATH="$APPDIR/usr/bin:$PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/bin:${LD_LIBRARY_PATH:-}"
export QT_MEDIA_BACKEND=ffmpeg
export PULSE_LATENCY_MSEC=30

exec "$APPDIR/usr/bin/Buzz" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# ── Step 5: Build AppImage ──────────────────────────────────────────────────
echo "==> Packaging AppImage..."
mkdir -p "$BUILD_DIR" "$PROJECT_DIR/dist"

APPIMAGETOOL="$BUILD_DIR/appimagetool-${ARCH}"
if [ ! -x "$APPIMAGETOOL" ]; then
    echo "==> Downloading appimagetool..."
    curl -fSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Download AppImage runtime (appimagetool's built-in download can fail)
RUNTIME="$BUILD_DIR/runtime-${ARCH}"
if [ ! -f "$RUNTIME" ]; then
    echo "==> Downloading AppImage runtime..."
    curl -fSL -o "$RUNTIME" \
        "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${ARCH}"
fi

# Fall back to extract-and-run when FUSE is unavailable (CI, containers) or
# unusable. Presence of `fusermount` is not enough: distros that ship only FUSE 3
# (Ubuntu 25.10+, where /usr/bin/fusermount is a symlink to fusermount3) still
# fail to mount appimagetool's FUSE 2 runtime. Probe it instead of guessing.
#
# The variable is APPIMAGE_EXTRACT_AND_RUN: it is read by the AppImage type-2
# runtime, which is what appimagetool (itself an AppImage) boots through. There
# is no APPIMAGETOOL_-prefixed variant -- setting one is silently ignored and
# the build dies with "Cannot mount AppImage, please check your FUSE setup."
EXTRA_ARGS=(--runtime-file "$RUNTIME" --no-appstream)
if [ "${CI:-}" = "true" ] || ! "$APPIMAGETOOL" --version >/dev/null 2>&1; then
    echo "==> FUSE unusable for appimagetool; falling back to extract-and-run"
    export APPIMAGE_EXTRACT_AND_RUN=1
fi

# If it still cannot start, neither mounting nor extraction works -- fail here
# with a clear message instead of midway through packaging.
if ! "$APPIMAGETOOL" --version >/dev/null 2>&1; then
    echo "ERROR: cannot run $APPIMAGETOOL (neither FUSE mount nor extract-and-run works)." >&2
    exit 1
fi

# Validate AppStream metadata ourselves in offline mode. appimagetool's internal
# appstream-util invocation performs network checks for remote screenshots,
# which breaks in proxied or restricted build environments even when the
# metadata itself is otherwise valid.
if command -v appstreamcli >/dev/null 2>&1; then
    echo "==> Validating AppStream metadata with appstreamcli (--no-net)..."
    appstreamcli validate --no-net "$APPSTREAM_FILE"
fi

if command -v appstream-util >/dev/null 2>&1; then
    echo "==> Validating AppStream metadata with appstream-util (--nonet)..."
    appstream-util validate-relax --nonet "$APPSTREAM_FILE"
fi

ARCH="$ARCH" "$APPIMAGETOOL" "${EXTRA_ARGS[@]}" "$APPDIR" "$OUTPUT"

echo "==> Done: $OUTPUT"
