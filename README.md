# my-plugins

**English** | [한국어](README-ko.md)

A Claude Code plugin marketplace by jahoonjin.

| Plugin | Version | Description |
|---|---|---|
| `my-agent` | 0.4.5 | Multi-agent task skill with human approval (HITL): plan → execute → verify → review |

## Requirements

- Claude Code with plugin support. Tested with Claude Code 2.1.311; the minimum version was not checked.
- Python 3.9 or later, available as `python3` in `PATH` (standard library only). Tested with Python 3.13.7. Hooks, scripts and the monitor server run on it.
- git, for the `dev` profile (base commit, worktrees, commit). Tested with git 2.50.1.
- macOS, for the monitor's browser window opening and the menu bar app. Tested on macOS 27.0.1. Linux and Windows were not tried: the hooks call `python3`, and the monitor opens windows with macOS commands (`open`, `osascript`).
- Optional, for the menu bar app only: Command Line Tools (`swiftc`) on macOS 12 or later; Xcode is not required. Tested with Swift 6.3.3; older Swift versions were not tried.

Nothing else is installed.

## Install

```bash
claude plugin marketplace add hamin-apple/my-plugins
claude plugin install my-agent@my-plugins
```

The repository is private, so you must be signed in with a GitHub account that has been invited to it.

A plugin cannot ship permission rules. For the risky-action prompts (G2: `git commit`, `git push`, `rm -rf`, package installs) and the denied commands (secret files, `--no-verify`, `git push --force`), merge the `ask` and `deny` lists of `plugins/my-agent/l4-tools-guards/permissions/permissions.json` into `permissions` in `~/.claude/settings.json` by hand. Without them those actions are not asked or blocked.

When you enable the plugin, Claude Code asks for one setting, the data folder (default `~/dev/log/my-agent`; change it later in `/config`). It holds everything my-agent keeps outside task folders: the project list (`projects.txt`), the run index (`active-index.json`), the monitor state, log and settings, the price override, the improvement list (`feedback.md`) and the retrospective report copies (`gate-report/`). A leading `~` is expanded. Nothing is written into the plugin's own folder. If the folder is changed, the old one is left as is and the new one is used from then on. If the setting is missing (for example with `--plugin-dir`), `~/dev/log/my-agent` is used. The environment variables `MA_TASKS_DIR` (data folder), `MA_PROJECTS_FILE`, `MA_FEEDBACK_FILE` and `MA_GATE_REPORT_DIR` win over the setting. A folder from an earlier version (`~/my-agent`) is not moved: move it to the new place, or set the Data folder to the old path.

## my-agent

The main session (L1) takes a request, runs plan → execute → verify → review in order, and asks the person in a popup at fixed points.

| Level | Members |
|---|---|
| L1 | Main session (`/my-agent` skill): runs the steps, delegates, asks, records |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: plans, judgments, decision analysis |
| L3 | `explorer` · `researcher` · `writer` · `coder`: one assigned piece of work each |
| L4 | Tools·MCP · hooks · permission rules · scripts: running, recording and blocking |

The whole architecture — each level's components, their roles and permissions, the steps and gates, and the format of every task file — is on one page, `docs/index.html`, published at <https://hamin-apple.github.io/my-plugins/>. `python3 tools/build-docs.py` builds it from the plugin files; run it again after changing them.

| Command | What it does |
|---|---|
| `/my-agent <request>` | Starts a new task. |
| `/my-agent --auto <request>` | Starts a new task and lets the main session answer the routine popups; the final acceptance (G3) and escalations still go to you. Combine with a profile flag if you like. |
| `/my-agent --dev <request>` | Starts a new task with the profile you name: `--general`, `--research` or `--dev`. Without a flag, the profile is picked from the request. |
| `/my-agent continue` | Continues the task in progress. |
| `/my-agent status` | Shows the task in progress and recent tasks. |
| `/my-agent:monitor` | Opens a local, read-only web page of task records. Also `status`, `stop`. |

Task records are kept in `docs/agent/<task ID>/` in the task location.
Finished tasks pile up there and in the monitor's list. To move tasks finished 30 days ago or more to `docs/agent/.archived/` (out of the list; move a folder back to bring it back):

```bash
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py --dry-run [--data-dir <folder>]   # list only
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py [--days N] [--data-dir <folder>]
```

Run by hand in a shell, the script does not know the setting. Unless your data folder is the default `~/dev/log/my-agent`, pass it with `--data-dir <folder>` so the script finds the project list.

## Update and remove

```bash
claude plugin marketplace update my-plugins
claude plugin update my-agent@my-plugins
claude plugin uninstall my-agent@my-plugins
```

## Repository layout

- `CLAUDE.md`: notes for development (folder roles, test commands, version rule)
- `.claude-plugin/marketplace.json`: plugin list
- `plugins/<name>/`: a plugin. Only this folder is copied on install.
- `tools/build-docs.py`, `tools/docs-template.html`: build the my-agent architecture page
- `docs/index.html`: the architecture page (generated; GitHub Pages source `main` · `/docs`)
- `tests/`: tests for `tools/`
- `docs/handoff/`: handoff notes for work continued in another environment
- `docs/agent/`: my-agent task records from this repository. Excluded from git.
- `plugins/my-agent/docs/reference.md`: sources of the reference documents. The local copies in `plugins/my-agent/docs/ref/` are excluded from git.

## License

[MIT](LICENSE)
