import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtDBus import QDBusConnection, QDBusInterface
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

POLL_INTERVAL_MS = 500
TERM_GRACE_SECONDS = 5
RELAUNCH_GRACE_SECONDS = 15
SCRIPT_UNLOAD_DELAY_MS = 1500
WATCH_SCRIPT = "traybird-watch"

COMMON_JS = """
function windows() {
    return typeof workspace.windowList === "function"
        ? workspace.windowList()
        : workspace.clientList();
}
function isThunderbird(w) {
    var cls = (w.resourceClass || "").toString().toLowerCase();
    return w.normalWindow && cls.indexOf("thunderbird") !== -1;
}
function connectAll(w, names, handler) {
    names.forEach(function (name) {
        if (w[name] && w[name].connect) {
            w[name].connect(handler);
        }
    });
}
function hide(w) {
    w.minimized = true;
    w.skipTaskbar = true;
    w.skipPager = true;
}
function show(w) {
    w.skipTaskbar = false;
    w.skipPager = false;
    w.minimized = false;
    if (typeof workspace.windowList === "function") {
        workspace.activeWindow = w;
    } else {
        workspace.activeClient = w;
    }
}
"""

SCRIPTS = {
    "show": COMMON_JS + "windows().filter(isThunderbird).forEach(function (w) { show(w); });",
    "toggle": COMMON_JS
    + """
var found = windows().filter(isThunderbird);
if (found.length > 0) {
    var hidden = found[0].skipTaskbar;
    found.forEach(function (w) {
        if (hidden) {
            show(w);
        } else {
            hide(w);
        }
    });
} else {
    var revealed = false;
    var reveal = function (w) {
        if (revealed || !w || !isThunderbird(w)) {
            return;
        }
        revealed = true;
        show(w);
    };
    var added = workspace.windowAdded || workspace.clientAdded;
    var activated = workspace.windowActivated || workspace.clientActivated;
    added.connect(function (w) {
        reveal(w);
        if (!revealed) {
            connectAll(w, ["windowClassChanged", "windowShown", "captionChanged"], function () {
                reveal(w);
            });
        }
    });
    activated.connect(reveal);
}
""",
    WATCH_SCRIPT: COMMON_JS
    + """
var GUARD_MS = 10000;
var hiddenAt = 0;
var done = false;
function guard(w) {
    connectAll(w, ["minimizedChanged", "activeChanged", "windowShown"], function () {
        if (Date.now() - hiddenAt < GUARD_MS && !w.minimized) {
            hide(w);
        }
    });
}
function consider(w) {
    if (done || !w || !isThunderbird(w)) {
        return;
    }
    done = true;
    hiddenAt = Date.now();
    hide(w);
    guard(w);
    print("traybird: hid " + w.caption);
}
windows().forEach(consider);
if (!done) {
    var added = workspace.windowAdded || workspace.clientAdded;
    var activated = workspace.windowActivated || workspace.clientActivated;
    added.connect(function (w) {
        consider(w);
        if (!done) {
            connectAll(w, ["windowClassChanged", "windowShown", "captionChanged"], function () {
                consider(w);
            });
        }
    });
    activated.connect(consider);
}
""",
}


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


class KWinScripts:
    def __init__(self):
        self.bus = QDBusConnection.sessionBus()
        self.scripting = QDBusInterface(
            "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", self.bus
        )
        self.directory = tempfile.mkdtemp(prefix="traybird-")

    def load(self, name):
        path = os.path.join(self.directory, f"{name}.js")
        with open(path, "w") as f:
            f.write(SCRIPTS[name])

        self.unload(name)
        reply = self.scripting.call("loadScript", path, name)
        args = reply.arguments()
        if not args or int(args[0]) < 0:
            print(f"KWin refused to load script {name}")
            return False

        script = QDBusInterface(
            "org.kde.KWin",
            f"/Scripting/Script{int(args[0])}",
            "org.kde.kwin.Script",
            self.bus,
        )
        script.call("run")
        return True

    def unload(self, name):
        self.scripting.call("unloadScript", name)

    def run_once(self, name):
        if self.load(name):
            QTimer.singleShot(SCRIPT_UNLOAD_DELAY_MS, lambda: self.unload(name))

    def close(self):
        self.unload(WATCH_SCRIPT)
        shutil.rmtree(self.directory, ignore_errors=True)


class TrayBird:
    def __init__(self, app):
        self.app = app
        self.kwin = KWinScripts()
        self.quitting = False
        self.kill_deadline = 0.0
        self.force_killed = False
        self.last_launch = 0.0

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
        self.kwin.load(WATCH_SCRIPT)
        if thunderbird_pid() is None:
            launch_thunderbird()
        self.last_launch = time.monotonic()

    def tick(self):
        if self.quitting:
            pid = thunderbird_pid()
            if pid is None:
                self.finish()
            elif not self.force_killed and time.monotonic() > self.kill_deadline:
                self.force_killed = True
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return

        if (
            thunderbird_pid() is None
            and time.monotonic() - self.last_launch > RELAUNCH_GRACE_SECONDS
        ):
            self.start_hidden()

    def on_activated(self, reason):
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        if self.quitting:
            return

        self.kwin.unload(WATCH_SCRIPT)
        if thunderbird_pid() is None:
            launch_thunderbird()
            self.last_launch = time.monotonic()
        self.kwin.load("toggle")

    def quit_thunderbird(self):
        pid = thunderbird_pid()
        self.quitting = True
        self.force_killed = False
        self.kill_deadline = time.monotonic() + TERM_GRACE_SECONDS
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def finish(self):
        self.tray.setVisible(False)
        self.kwin.close()
        self.app.quit()

    def shutdown(self):
        self.kwin.unload(WATCH_SCRIPT)
        self.kwin.run_once("show")
        QTimer.singleShot(400, self.finish)


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

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
