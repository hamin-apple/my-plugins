# my-agent menu bar app

A small menu bar app for the my-agent monitor. It only shows state and runs `monitor-up.py`; it never writes task data.

## What it shows

The menu bar icon shows the number of running tasks (`off` when the monitor server is off). It reacts to the click:

- **Left click** opens the mini window, or brings it to the front if it is already open (the first click works even when another app is active). The app does not open the window by itself at start.
- **Right click or Ctrl+left click** shows the menu described below.

### Mini window

A window with a thin title-less header: a `List | Detail` switch and a pin button. Drag the background to move it.

- **List** (default about 300x640) is native. One line per task: status mark (`?` waiting for an answer, a dot for running, `✓` done, `■` stopped or unknown), task ID (one line, shortened in the middle), current step (`5. Execute`, `Done`, or `–` when unknown), elapsed time (`38m`, `1h 5m`, `2d 3h`) and an 8-cell progress bar. Running and waiting tasks come first; the rest keep the server order (newest first).
- The status mark and the current bar cell of running and waiting lines blink slowly (opacity 1, 0.3, 1 every 1.4 s, like the running dot of the web monitor). Done, stopped and unknown lines do not blink. With macOS Reduce Motion on, nothing blinks.
- The filter `All | Running | Done | Stopped` sits under the header. A task with no status shows only under All. With the server off the list shows `Monitor server is off`; with no match it shows `No tasks` or `No done tasks` and so on.
- Clicking a line switches the same window to **Detail** with that task selected. Clicking the same line again selects it again.
- **Detail** (default about 1000x700) is the web monitor itself in a web view, so it looks the same as in the browser. Choosing Detail with the switch keeps the task already shown. With the server off it shows `Monitor server is off`; when the server comes back (even on another port) the page is loaded again. The web state of Detail (selection, scroll) is not kept across app restarts; only the frame is.
- **Pin** keeps the window above other apps' windows; unpinned it is a normal window.
- The position and size are remembered separately for List and Detail. Switching mode moves to that mode's frame. A saved frame that is off every connected screen is moved back inside the visible screen, and one larger than the screen is shrunk to it.
- The list refreshes every 5 s, in the same poll as the menu, with the same server lookup (`monitor.json`, then ports 8765 to 8775).

Only screen settings are stored, in the defaults domain `my-agent.monitor-menubar`: `mode`, `pinned`, `frame.list`, `frame.detail`. Task data is never written. Check them with `defaults read my-agent.monitor-menubar`.

### Menu (right click)

- The menu has one line per running task, like `261025-monitor-popup-window · 3. Plan`. Choosing a line runs `monitor-up.py --open --task <key>`, which opens the monitor with that task selected.
- `Browser ▸` (below `Open Monitor`) has `Default Browser`, `Safari` and `Chrome (App Window)`; the current value is checked. Choosing one runs `monitor-up.py set-browser <value>`, which changes only the `browser` key of `monitor-config.json`. Every way of opening the monitor (this menu, my-agent's automatic start, `monitor-up.py`) follows it. The submenu is shown even when the server is off or no task is running.
- With no running task the menu shows `No running tasks`. With the server off it shows `Monitor server is off`.
- `Open Monitor` runs `monitor-up.py --open`. `Quit` quits the app only; the server keeps running.
- When the app starts it runs `monitor-up.py --no-open`, so the server is up without a window. The menu refreshes every 5 s. The menu and the icon never blink.

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
menubar/build/my-agent-menubar --print-list [--filter all|running|done|stopped] [--ports A-B]
                                               # print the List lines (symbol, ID, step, elapsed, bar, pulse or -, key), then exit
menubar/build/my-agent-menubar --fit-frame 3000,100,300,640 0,0,1512,944
                                               # saved frame first, then screens (x,y,w,h); print the frame moved inside a screen
menubar/build/my-agent-menubar --print-detail loaded=8765 port=8765 applied=1 seq=2 key=<key>
                                               # print what Detail would do: off, load <url>, select <js> or none
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
defaults delete my-agent.monitor-menubar    # forget mode, pin and window frames
```

Then quit the running app from its menu (`Quit`).
