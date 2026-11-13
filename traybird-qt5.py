import os
import signal
import subprocess
import sys
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

POLL_INTERVAL_MS = 500
WINDOW_WAIT_ATTEMPTS = 120
TERM_GRACE_SECONDS = 5


def run(cmd):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def thunderbird_pid():
    out = run(["pgrep", "-o", "-x", "thunderbird(-bin)?"])
    return int(out) if out.isdigit() else None


def launch_thunderbird():
    try:
        subprocess.Popen(
            ["thunderbird"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"Failed to start Thunderbird: {e}")


def find_window():
    pid = thunderbird_pid()
    if pid is None:
        return None
    for line in run(["wmctrl", "-lpx"]).splitlines():
        cols = line.split(None, 5)
        if len(cols) < 4:
            continue
        if "thunderbird" in cols[3].lower() or cols[2] == str(pid):
            return cols[0]
    return None


def is_hidden(window_id):
    state = run(["xprop", "-id", window_id, "_NET_WM_STATE"])
    return "_NET_WM_STATE_SKIP_TASKBAR" in state


def hide_window(window_id):
    run(["xdotool", "windowminimize", window_id])
    run(["wmctrl", "-i", "-r", window_id, "-b", "add,skip_taskbar,skip_pager"])


def show_window(window_id):
    run(["wmctrl", "-i", "-r", window_id, "-b", "remove,skip_taskbar,skip_pager"])
    run(["xdotool", "windowmap", window_id])
    run(["xdotool", "windowactivate", window_id])


class TrayBird:
    def __init__(self, app):
        self.app = app
        self.pending_hide = False
        self.hide_attempts = 0
        self.quitting = False
        self.kill_deadline = 0.0
        self.force_killed = False

        icon = QIcon.fromTheme("mail-unread", QIcon.fromTheme("mail-unread-symbolic"))
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("TrayBird")
        self.tray.activated.connect(self.on_activated)

        self.menu = QMenu()
        self.quit_action = QAction("Quit TrayBird")
        self.quit_action.triggered.connect(self.quit_thunderbird)
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.setVisible(True)

        self.timer = QTimer()
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

        self.start_hidden()

    def start_hidden(self):
        if thunderbird_pid() is None:
            launch_thunderbird()
        self.pending_hide = True
        self.hide_attempts = 0

    def tick(self):
        if self.quitting:
            pid = thunderbird_pid()
            if pid is None:
                self.tray.setVisible(False)
                self.app.quit()
            elif not self.force_killed and time.monotonic() > self.kill_deadline:
                self.force_killed = True
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return

        if self.pending_hide:
            self.hide_attempts += 1
            window_id = find_window()
            if window_id:
                hide_window(window_id)
                self.pending_hide = False
            elif self.hide_attempts >= WINDOW_WAIT_ATTEMPTS:
                self.pending_hide = False
        elif thunderbird_pid() is None:
            self.start_hidden()

    def on_activated(self, reason):
        if reason != QSystemTrayIcon.Trigger:
            return
        if self.quitting or self.pending_hide:
            return

        window_id = find_window()
        if not window_id:
            self.start_hidden()
            return

        if is_hidden(window_id):
            show_window(window_id)
        else:
            hide_window(window_id)

    def quit_thunderbird(self):
        pid = thunderbird_pid()
        self.quitting = True
        self.pending_hide = False
        self.force_killed = False
        self.kill_deadline = time.monotonic() + TERM_GRACE_SECONDS
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def shutdown(self):
        window_id = find_window()
        if window_id and is_hidden(window_id):
            show_window(window_id)
        self.tray.setVisible(False)
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray available")
        return 1

    tray = TrayBird(app)

    signal.signal(signal.SIGTERM, lambda *_: tray.shutdown())
    signal.signal(signal.SIGINT, lambda *_: tray.shutdown())

    keepalive = QTimer()
    keepalive.setInterval(200)
    keepalive.timeout.connect(lambda: None)
    keepalive.start()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
