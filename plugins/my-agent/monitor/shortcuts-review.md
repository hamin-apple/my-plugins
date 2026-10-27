# Opening the monitor from Shortcuts

Can the macOS Shortcuts app open the monitor, with a keyboard shortcut? Yes, with one shortcut and one shell command. This note records how, and compares it with the menu bar app (`menubar/README.md`). No shortcut file is shipped.

## One shortcut: Run Shell Script

1. In Shortcuts, create a shortcut, for example "my-agent monitor".
2. Add the action "Run Shell Script". Shell `zsh`, input not used.
3. Script:

   ```sh
   python3 ~/dev/my-plugins/plugins/my-agent/monitor/monitor-up.py --open
   ```

`--open` starts the server if needed and always opens the monitor the way `monitor-config.json` says (window by default). Add `--task <key>` to open one task; the key changes per task, so a fixed shortcut cannot do that.

Running shell scripts needs the Shortcuts setting "Allow Running Scripts" (in Shortcuts settings, Advanced). Without it the action fails. The first run may also ask for permission to control Safari (see the menu bar README).

## Keyboard shortcut (Add Keyboard Shortcut)

Open the shortcut's details (Details, the "i" button in the editor), choose "Add Keyboard Shortcut" and press the keys. Pick a combination that includes Command or Control, since the key works system-wide.

## Running it: menu bar, Spotlight, `shortcuts run`

- Menu bar: in the details, turn on "Pin in Menu Bar". The Shortcuts icon then lists the shortcut.
- Spotlight: type the shortcut's name and press Return.
- Terminal: `shortcuts run "my-agent monitor"` (list names with `shortcuts list`).

## Using the existing "Open URLs" shortcut

A shortcut made of the "Open URLs" action with `http://127.0.0.1:8765/` needs no script permission, but:

- It always opens a tab in the default browser, never a sized window.
- It does not start the server. If the monitor is off, the page does not load.
- The port is fixed. If 8765 is busy and the monitor took 8766 or higher, it opens the wrong address.
- It cannot select a task.

## Shortcuts vs the menu bar app

| | Shortcuts | Menu bar app |
|---|---|---|
| Build needed | no | swiftc once |
| Always visible (running count) | no | yes |
| Open one task | no (needs a key) | yes, one line per task |
| Starts the server at login | no | yes (login item) |
| Permissions | allow running scripts | Safari automation (Safari only) |
| Maintenance | none, but the script path is typed by hand | rebuild if the folder moves |

## Conclusion

Shortcuts is enough if you only want a key press that opens the monitor: it needs no build and no code, and `monitor-up.py --open` already starts the server and applies the window or tab setting. It cannot show how many tasks are running or open a particular task. The menu bar app does both and can start the server at login, at the cost of one build. They do not conflict, so use either or both. This task adds the menu bar app and does not create a shortcut file.
