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

# ── Step 3: Desktop integration ─────────────────────────────────────────────
# Desktop file — Exec must be just the binary name for AppImage spec
cat > "$APPDIR/io.github.chidiwilliams.Buzz.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Buzz
GenericName=Audio Transcriber
Comment=Transcribe and translate audio offline
Exec=Buzz
Icon=io.github.chidiwilliams.Buzz
Terminal=false
Categories=AudioVideo;Audio;
MimeType=audio/mpeg;audio/wav;audio/ogg;audio/flac;video/mp4;video/webm;
EOF
cp "$APPDIR/io.github.chidiwilliams.Buzz.desktop" "$APPDIR/usr/share/applications/"

# Icon (SVG at AppDir root + XDG hicolor location)
cp "$PROJECT_DIR/share/icons/io.github.chidiwilliams.Buzz.svg" "$APPDIR/"
cp "$PROJECT_DIR/share/icons/io.github.chidiwilliams.Buzz.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/"

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

# Use APPIMAGETOOL_EXTRACT_AND_RUN when FUSE is unavailable (CI, containers)
EXTRA_ARGS=(--runtime-file "$RUNTIME" --no-appstream)
if [ "${CI:-}" = "true" ] || ! command -v fusermount &>/dev/null; then
    export APPIMAGETOOL_EXTRACT_AND_RUN=1
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
