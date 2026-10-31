# my-agent-tray

OS shells for the [my-agent](../my-agent/README.md) monitor: a macOS menu bar app now, a Windows tray app reserved (`windows/`). This plugin adds no skills, commands or agents to Claude Code.

Install: `claude plugin install my-agent-tray@my-plugins`.

Needs my-agent 0.5.0 or later (the shell reads `root` from `monitor.json`).

## Build (macOS)

Needs `/usr/bin/swiftc` (Command Line Tools).

```sh
cd plugins/my-agent-tray
sh macos/menubar/build.sh
```

## Login item

```sh
sh macos/menubar/login-item.sh install [<data folder>]
```

Users of the 0.4.x menu bar app run `login-item.sh install` again: the old login item points at a deleted binary (same label, so the new one replaces it).

After a marketplace install or update of my-agent-tray the plugin folder changes: rebuild (`sh macos/menubar/build.sh`) and run `sh macos/menubar/login-item.sh install` again from the new folder.

## Notes

- With `"autostart": false` in `monitor-config.json`, the app's start launch does nothing; `Open Monitor` starts the monitor.
- After `/my-agent:monitor stop` (which deletes `monitor.json`) the app cannot start the monitor until `/my-agent:monitor` runs once.

More: [macos/menubar/README.md](macos/menubar/README.md).

## Test

```sh
cd plugins/my-agent-tray && python3 -m unittest discover -s tests
```

The tests skip without `/usr/bin/swiftc` or without the my-agent plugin next to this one.
