#!/bin/sh
set -eu

SRC_DIR=$(cd "$(dirname "$0")" && pwd)
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"

if [ ! -f "$SRC_DIR/traybird.py" ] || [ ! -f "$SRC_DIR/traybird.desktop" ]; then
    echo "traybird.py and traybird.desktop must be next to install.sh" >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$APP_DIR"

install -m 755 "$SRC_DIR/traybird.py" "$BIN_DIR/traybird.py"

sed "s|@BIN_DIR@|$BIN_DIR|g" "$SRC_DIR/traybird.desktop" > "$APP_DIR/traybird.desktop"
chmod 644 "$APP_DIR/traybird.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed $BIN_DIR/traybird.py"
echo "Installed $APP_DIR/traybird.desktop"
