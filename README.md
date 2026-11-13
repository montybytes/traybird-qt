# TrayBird

A system tray icon inspired by ThunderTray that keeps Thunderbird out of your way. Thunderbird starts hidden, a left click shows or hides its window, and a right click quits it. I made this because I like Thunderbird but was upset at its lack of system tray support/background running mode. I wanted it to be present so that it can show its own notifications but still be away from my desktop

## Behavior

- **On start:** TrayBird launches Thunderbird if it isn't running and hides it, minimized and removed from the taskbar and pager.
- **Left click:** toggles the Thunderbird window.
- **Right click → Quit:** kills Thunderbird process started by the script and exits TrayBird. Nothing is restarted.
- **Thunderbird closed any other way** (window close button, File → Quit, a crash): TrayBird starts it again but hidden.

On the Qt6 version, if you click the icon while Thunderbird is restarting, the window is shown as soon as it opens, so you don't need to click again.

## Requirements

|                 | Qt5 version                                | Qt6 version     |
| --------------- | ------------------------------------------ | --------------- |
| Session         | X11                                        | Wayland         |
| Python bindings | `python3-pyqt5`                            | `python3-pyqt6` |
| Other tools     | `wmctrl`, `xdotool`, `x11-utils`, `procps` | `procps`        |

Thunderbird must be on your `PATH` as `thunderbird`. A non-snap install is expected, but a snap should also work.

#### Qt 6 Dependencies

```sh
sudo apt install python3-pyqt6
```

#### Qt 5 Dependencies

```sh
sudo apt install python3-pyqt5 wmctrl xdotool x11-utils procps
```

## Install

Clone this repo (or download and unzip)

```
git clone https://github.com/montybytes/traybird-qt.git
```

Then run:

```sh
sh install.sh
```

The installer checks which Python Qt bindings are available. It prefers Qt6 and falls back to Qt5. It copies the matching script to `~/.local/bin/traybird.py` and the desktop entry to `~/.local/share/applications/traybird.desktop`.

If both are installed, you can force a version:

```sh
sh install.sh 5 # Qt 5 / Plasma 5
sh install.sh 6
```

`traybird.desktop` contains `@BIN_DIR@`, which the installer replaces with your `~/.local/bin` path.

## Run

Start **TrayBird** from the application menu, or run:

```sh
python3 ~/.local/bin/traybird.py
```

### Start at login

Copy the desktop file to your autostart folder:

```sh
cp ~/.local/share/applications/traybird.desktop ~/.config/autostart/
```

If the icon sometimes fails to appear after login, add a delay to the `Exec` line in the desktop file:

```sh
Exec=sh -c "sleep 5 && python3 /home/USERNAME/.local/bin/traybird &"
```

## Limitations

- On the Qt6 version, clicking the icon in the first 10 seconds after Thunderbird starts can race with the re-hide guard. It usually works on the first click, but may take a second.
- Closing Thunderbird restarts it from scratch, so there is a few seconds' wait before its window can appear. The tray cannot make that instant.
- Quit always quits both Thunderbird and TrayBird. There is no option to quit only the tray.

## Uninstall

```
rm ~/.local/bin/traybird
rm ~/.local/share/applications/traybird.desktop
rm -f ~/.config/autostart/traybird.desktop
```
