# my-agent menu bar app

A small menu bar app for the my-agent monitor (plugin `my-agent-tray`). It only shows state and runs `monitor-up.py`; it never writes task data.

## What it shows

The menu bar icon shows the number of running tasks (`off` when the monitor server is off). It reacts to the click:

- **Left click** shows or hides the mini window. If the window is in front (no other window covers any part of it, or it is pinned) the click hides it; otherwise (closed, hidden, minimized, covered or on another space) it opens it or brings it to the front. The first click works even when another app is active. The app does not open the window by itself at start. In the mini window, too, the first click acts right away: on the filter, the List/Detail switch, the pin and a row.
- **Right click or Ctrl+left click** shows the menu described below.

### Mini window

A window with a thin title-less header: a `List | Detail` switch and a pin button. Drag the background to move it.

- **List** (default width 300, height set by the number of lines, up to 7 lines) is native. One line per task: status mark (`?` waiting for an answer, a dot for running, `✓` done, `■` stopped or unknown), task ID (one line), elapsed time (`38m`, `1h 5m`, `2d 3h`) and an 8-cell progress bar. The step name is not shown in the window; the status shows in the mark color and the bar. The elapsed time takes only the width of its text, the ID gets all the remaining width and is shortened in the middle only when it still does not fit. Running and waiting tasks come first; the rest keep the server order (newest first).
- The List height fits the visible lines (after the filter) up to 7: header + filter row + lines x line height, at most 7 lines. With more than 7 lines the window stays 7 lines tall and the list scrolls; every line stays in the list. The top edge stays fixed; the bottom edge grows or shrinks (a short animation) when the number of lines changes, by a refresh or by the filter. A refresh that keeps the same number of lines does not touch the window. If the height is more than the visible height of the screen the window is only as tall as the screen and the list scrolls. With no lines (no tasks, no match, server off) it shrinks to the one-line notice. If the window sits so near the bottom of the screen that the header, filter row and one line would not show, the top edge is moved up. Moving the window to another screen fits it to that screen. Fitting waits while you drag the window.
- In List you can change only the width; the height cannot be dragged. List remembers the position (top edge) and the width only, and opens at that position and width with the height fitted to the current lines. A saved height from an older version is ignored. Detail still remembers its position and size.
- Status colors (the same values as the web monitor's `--st-*`, set in `statusPalette` in `Sources/ListModel.swift`):

  | State | Used for | Light | Dark |
  | --- | --- | --- | --- |
  | `run` running (orange) | dot, current bar cell | `#c25e00` | `#ffa94d` |
  | `wait` waiting for an answer (red) | `?`, current bar cell | `#d1242f` | `#ff6b6b` |
  | `done` done (blue) | `✓`, all 8 bar cells | `#2552c9` | `#7ea3ff` |
  | `stop` stopped (dark gray) | `■`, stopped bar cell | `#4b5563` | `#c9d1d9` |
  | `past` passed cell (green) | passed cells of running, waiting and stopped tasks | `#1d7a3e` | `#5fd08a` |

  A cell not reached yet is a faint gray; a task with no status shows a gray `■`.
- The status mark and the current bar cell of running and waiting lines blink slowly (opacity 1, 0.3, 1 every 1.4 s, like the running dot of the web monitor). Done, stopped and unknown lines do not blink. With macOS Reduce Motion on, nothing blinks.
- The filter `All | Running | Done | Stopped` sits under the header. A task with no status shows only under All. With the server off the list shows `Monitor server is off`; with no match it shows `No tasks` or `No done tasks` and so on.
- Clicking a line switches the same window to **Detail** with that task selected. Clicking the same line again selects it again.
- **Detail** (default about 1000x700) is the web monitor itself in a web view, so it looks the same as in the browser. Choosing Detail with the switch keeps the task already shown. With the server off it shows `Monitor server is off`; when the server comes back (even on another port) the page is loaded again. The web state of Detail (selection, scroll) is not kept across app restarts; only the frame is.
- **Components window:** in Detail, `4 · Log`, the button `↗ Components` opens one extra window, "Components · my-agent" (first time 560x640), that follows the replay. Clicking the button again brings it to front. It floats above other apps while the main window is pinned and stops floating when unpinned. Its size and position are remembered across restarts (key `frame.components`). Closing it, or closing the main window, closes it; the next click opens it again. In the browser the page opens its own popup as before.
- **Pin** keeps the window above other apps' windows; unpinned it is a normal window.
- The frame is remembered separately for List (position and width) and Detail (position and size). Switching mode moves to that mode's frame. A saved frame that is off every connected screen is moved back inside the visible screen, and one larger than the screen is shrunk to it.
- The list refreshes every 5 s, in the same poll as the menu, with the same server lookup (`monitor.json`, then ports 8765 to 8775).

Only screen settings are stored, in the defaults domain `my-agent.monitor-menubar`: `mode`, `pinned`, `frame.list`, `frame.detail`, `frame.components`. Task data is never written. Check them with `defaults read my-agent.monitor-menubar`.

### Menu (right click)

- The menu has one line per running task, like `261025-monitor-popup-window · 3. Plan`. Choosing a line runs `monitor-up.py --open --task <key>`, which opens the monitor with that task selected.
- `Browser ▸` (below `Open Monitor`) has `Default Browser`, `Safari` and `Chrome (App Window)`; the current value is checked. Choosing one runs `monitor-up.py set-browser <value>`, which changes only the `browser` key of `monitor-config.json`. Every way of opening the monitor (this menu, my-agent's automatic start, `monitor-up.py`) follows it. The submenu is shown even when the server is off or no task is running.
- With no running task the menu shows `No running tasks`. With the server off it shows `Monitor server is off`.
- `Open Monitor` runs `monitor-up.py --open`. `Quit` quits the app only; the server keeps running.
- When the app starts it runs `monitor-up.py --no-open`, so the server is up without a window. The menu refreshes every 5 s. The menu and the icon never blink.

How a window opens (window or tab, per browser) is decided by `monitor-up.py`; see [the monitor README](../../../my-agent/monitor/README.md).

## Build

Needs the Command Line Tools (`xcode-select --install`) for the system `/usr/bin/swiftc`. Nothing else is installed.

```sh
cd ~/dev/my-plugins/plugins/my-agent-tray
sh macos/menubar/build.sh
```

The result is `macos/menubar/build/my-agent-menubar`. The script writes only under `macos/menubar/build/`, and bakes in only the `python3` found in `PATH`; it does not bake in the monitor folder, so the build keeps working after my-agent is updated or moved. It needs my-agent 0.5.0 or later (the app reads `root` from `monitor.json`).

## Install

There is no copy step. The built binary is used where it is. To try it by hand:

```sh
macos/menubar/build/my-agent-menubar
macos/menubar/build/my-agent-menubar --print-menu    # print the menu and the commands it would run, then exit
macos/menubar/build/my-agent-menubar --print-list [--filter all|running|done|stopped] [--ports A-B]
                                               # print the List lines (symbol, ID, step, elapsed, bar, pulse or -, key), then exit
                                               # (the step column is printed here only; the window does not show it)
macos/menubar/build/my-agent-menubar --print-list --tones
                                               # add two columns: the mark's tone and 8 bar tone letters (p past, r run, w wait, b done, s stop, -)
macos/menubar/build/my-agent-menubar --list-frame 1180,220,300,640 12 0,0,1512,944
                                               # saved frame, number of lines, then screens; print the fitted frame (at most 7 lines tall) and fit or scroll (scroll: not every line fits, more than 7 lines or cut by the screen)
macos/menubar/build/my-agent-menubar --print-palette # print tone, light, dark for the status colors
macos/menubar/build/my-agent-menubar --fit-frame 3000,100,300,640 0,0,1512,944
                                               # saved frame first, then screens (x,y,w,h); print the frame moved inside a screen
macos/menubar/build/my-agent-menubar --print-detail loaded=8765 port=8765 applied=1 seq=2 key=<key>
                                               # print what Detail would do: off, load <url>, select <js> or none
```

## Login item

```sh
sh macos/menubar/login-item.sh install [<data folder>]   # start at login (folder default ~/dev/log/my-agent)
sh macos/menubar/login-item.sh status      # loaded / not loaded
sh macos/menubar/login-item.sh uninstall   # stop starting at login
```

`install` and `uninstall` write outside the repository: `~/Library/LaunchAgents/my-agent.monitor-menubar.plist` (a launchd user agent, `RunAtLoad`, no `KeepAlive`). `install` needs a build first and loads the agent right away. The app reads the data folder from `MA_TASKS_DIR`, then `CLAUDE_PLUGIN_OPTION_DATA_DIR`, then `~/dev/log/my-agent`; a login item has no plugin environment, so `install` writes the folder (a leading `~` is expanded) into the plist as `CLAUDE_PLUGIN_OPTION_DATA_DIR`, and the `monitor-up.py` the app starts inherits it. Use the same folder as the my-agent `data_dir` setting. After changing that setting, run `install <new folder>` again.

## Safari permission

If Safari is the default browser, the first window opened through the app (or `monitor-up.py`) makes macOS ask whether to allow controlling Safari (Automation). If you refuse, or do not answer within 5 s, the monitor opens in a browser tab instead. You can change it later in System Settings, Privacy & Security, Automation.

## Remove

```sh
sh macos/menubar/login-item.sh uninstall
rm -r macos/menubar/build
defaults delete my-agent.monitor-menubar    # forget mode, pin and window frames
```

Then quit the running app from its menu (`Quit`).

## Finding the monitor

The app does not know where my-agent is installed. It finds the monitor through the state file `<data folder>/monitor.json` (`port`, `root`) and `/api/health`: the port from `monitor.json` is tried first, then 8765 to 8775. The folder it runs `monitor-up.py` from is the `root` that the monitor found reports in `/api/health`, else the `root` in `monitor.json`; a `root` counts only when it is a string and `<root>/monitor-up.py` exists. If neither gives a folder, the menu shows `Monitor folder unknown: run /my-agent:monitor once`, `Open Monitor`, the task lines and `Browser` are disabled, and the app starts nothing.

After `/my-agent:monitor stop` (which deletes `monitor.json`) nothing answers and no state file exists, so the app shows `Monitor folder unknown` and cannot start the monitor until `/my-agent:monitor` runs once.

A monitor that still runs from before a my-agent update keeps reporting the old plugin folder. Restart it (`/my-agent:monitor stop`, then `/my-agent:monitor`) after updating my-agent, so the app uses the new folder.

With `"autostart": false` in `monitor-config.json`, the `monitor-up.py --no-open` the app runs at start does nothing; `Open Monitor` starts the monitor.

Users of the 0.4.x menu bar app: the old login item points at a deleted binary; run `login-item.sh install` again (same label, so it replaces the old one).

After a marketplace install or update of my-agent-tray the plugin folder changes: rebuild (`sh macos/menubar/build.sh`) and run `sh macos/menubar/login-item.sh install` again from the new folder.
