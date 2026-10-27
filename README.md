# my-plugins

**English** | [한국어](README-ko.md)

A Claude Code plugin marketplace by jahoonjin.

| Plugin | Version | Description |
|---|---|---|
| `my-agent` | 0.3.1 | Multi-agent task skill with human approval (HITL): plan → execute → verify → review |

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

## my-agent

The main session (L1) takes a request, runs plan → execute → verify → review in order, and asks the person in a popup at fixed points.

| Level | Members |
|---|---|
| L1 | Main session (`/my-agent` skill): runs the steps, delegates, asks, records |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: plans, judgments, decision analysis |
| L3 | `explorer` · `researcher` · `writer` · `coder`: one assigned piece of work each |
| L4 | Tools·MCP · hooks · permission rules · scripts: running, recording and blocking |

| Command | What it does |
|---|---|
| `/my-agent <request>` | Starts a new task. |
| `/my-agent continue` | Continues the task in progress. |
| `/my-agent status` | Shows the task in progress and recent tasks. |
| `/my-agent:monitor` | Opens a local, read-only web page of task records. Also `status`, `stop`. |

Task records are kept in `docs/agent/<task ID>/` in the task location.
Finished tasks pile up there and in the monitor's list. To move tasks finished 30 days ago or more to `docs/agent/.archived/` (out of the list; move a folder back to bring it back):

```bash
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py --dry-run   # list only
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py [--days N]
```

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
- `docs/handoff/`: handoff notes for work continued in another environment
- `docs/agent/`: my-agent task records from this repository. Excluded from git.
