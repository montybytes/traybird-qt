#!/bin/sh
set -eu

SRC_DIR=$(cd "$(dirname "$0")" && pwd)
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_SRC="$SRC_DIR/traybird.desktop"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found (sudo apt install python3)" >&2
    exit 1
fi

has_qt6() {
    python3 -c "import PyQt6.QtWidgets, PyQt6.QtDBus" >/dev/null 2>&1
}

has_qt5() {
    python3 -c "import PyQt5.QtWidgets" >/dev/null 2>&1
}

QT="${1:-}"

case "$QT" in
    "")
        if has_qt6; then
            QT=6
        elif has_qt5; then
            QT=5
        else
            echo "No Qt Python bindings found." >&2
            echo "Install one of:" >&2
            echo "  sudo apt install python3-pyqt6   (Qt6, Wayland)" >&2
            echo "  sudo apt install python3-pyqt5   (Qt5, X11)" >&2
            exit 1
        fi
        ;;
    5)
        has_qt5 || { echo "PyQt5 not found (sudo apt install python3-pyqt5)" >&2; exit 1; }
        ;;
    6)
        has_qt6 || { echo "PyQt6 not found (sudo apt install python3-pyqt6)" >&2; exit 1; }
        ;;
    *)
        echo "Usage: sh install.sh [5|6]" >&2
        exit 1
        ;;
esac

QT_VERSION=$(python3 -c "from PyQt$QT.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)" 2>/dev/null || echo "unknown")
echo "Using Qt$QT (Qt $QT_VERSION)"

SCRIPT_SRC="$SRC_DIR/traybird-qt$QT.py"

if [ ! -f "$SCRIPT_SRC" ] || [ ! -f "$DESKTOP_SRC" ]; then
    echo "traybird-qt$QT.py and traybird.desktop must be next to install.sh" >&2
    exit 1
fi

if [ "$QT" = "5" ]; then
    for tool in wmctrl xdotool xprop pgrep; do
        command -v "$tool" >/dev/null 2>&1 || echo "Warning: $tool not found (sudo apt install wmctrl xdotool x11-utils procps)"
    done
fi

mkdir -p "$BIN_DIR" "$APP_DIR"

install -m 755 "$SCRIPT_SRC" "$BIN_DIR/traybird.py"

sed "s|@BIN_DIR@|$BIN_DIR|g" "$DESKTOP_SRC" > "$APP_DIR/traybird.desktop"
chmod 644 "$APP_DIR/traybird.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed $SCRIPT_SRC as $BIN_DIR/traybird.py"
echo "Installed $APP_DIR/traybird.desktop"
