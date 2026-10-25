# my-agent menu bar app

A small menu bar app for the my-agent monitor. It only shows state and runs `monitor-up.py`; it never writes task data.

## What it shows

- The icon shows the number of running tasks. When the monitor server is off it shows `off`.
- The menu has one line per running task, like `261025-monitor-popup-window · 3. Plan`. Choosing a line runs `monitor-up.py --open --task <key>`, which opens the monitor with that task selected.
- `Browser ▸` (below `Open Monitor`) has `Default Browser`, `Safari` and `Chrome (App Window)`; the current value is checked. Choosing one runs `monitor-up.py set-browser <value>`, which changes only the `browser` key of `monitor-config.json`. Every way of opening the monitor (this menu, my-agent's automatic start, `monitor-up.py`) follows it. The submenu is shown even when the server is off or no task is running.
- With no running task the menu shows `No running tasks`. With the server off it shows `Monitor server is off`.
- `Open Monitor` runs `monitor-up.py --open`. `Quit` quits the app only; the server keeps running.
- When the app starts it runs `monitor-up.py --no-open`, so the server is up without a window. The menu refreshes every 5 s.

How a window opens (window or tab, per browser) is decided by `monitor-up.py`; see `../README.md`.

## Build

Needs the Command Line Tools (`xcode-select --install`) for the system `/usr/bin/swiftc`. Nothing else is installed.

```sh
cd ~/dev/my-plugins/plugins/my-agent/monitor
sh menubar/build.sh
```

The result is `menubar/build/my-agent-menubar`. The script writes only under `menubar/build/`, and bakes in this folder's path and the `python3` found in `PATH`. Rebuild after moving the folder.

## Install

There is no copy step. The built binary is used where it is. To try it by hand:

```sh
menubar/build/my-agent-menubar
menubar/build/my-agent-menubar --print-menu    # print the menu and the commands it would run, then exit
```

## Login item

```sh
sh menubar/login-item.sh install     # start at login
sh menubar/login-item.sh status      # loaded / not loaded
sh menubar/login-item.sh uninstall   # stop starting at login
```

`install` and `uninstall` write outside the repository: `~/Library/LaunchAgents/my-agent.monitor-menubar.plist` (a launchd user agent, `RunAtLoad`, no `KeepAlive`). `install` needs a build first and loads the agent right away.

## Safari permission

If Safari is the default browser, the first window opened through the app (or `monitor-up.py`) makes macOS ask whether to allow controlling Safari (Automation). If you refuse, or do not answer within 5 s, the monitor opens in a browser tab instead. You can change it later in System Settings, Privacy & Security, Automation.

## Remove

```sh
sh menubar/login-item.sh uninstall
rm -r menubar/build
```

Then quit the running app from its menu (`Quit`).
