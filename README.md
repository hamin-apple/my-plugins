# my-plugins

**English** | [한국어](README-ko.md)

A Claude Code plugin marketplace by minpple.

| Plugin | Version | Description |
|---|---|---|
| `my-agent` | 0.12.0 | Multi-agent task skill with human approval (HITL): plan → execute → verify → review |
| `my-agent-tray` | 0.1.4 | macOS menu bar app for the my-agent monitor (optional; needs my-agent 0.5.0 or later) |

## Requirements

- Claude Code with plugin support. Tested with Claude Code 2.1.311; the minimum version was not checked.
- Python 3.9 or later, available as `python3` in `PATH` (standard library only). Tested with Python 3.13.7. Hooks, scripts and the monitor server run on it.
- git, for the `dev` profile (base commit, worktrees, commit). Tested with git 2.50.1.
- macOS, for the monitor's window opening. Tested on macOS 27.0.1. On other platforms the monitor opens a tab through the standard browser opener; this was not tried. Linux and Windows were not tried: the hooks call `python3`.
- Optional, for the menu bar app (the `my-agent-tray` plugin) only: Command Line Tools (`swiftc`) on macOS 12 or later; Xcode is not required. Tested with Swift 6.3.3; older Swift versions were not tried.
- Optional, to use my-agent in Codex: Codex CLI with plugin support. Tested with codex-cli 0.166.0; other versions were not tried.

Nothing else is installed.

## Install

```bash
claude plugin marketplace add minpple/my-plugins
claude plugin install my-agent@my-plugins
claude plugin install my-agent-tray@my-plugins   # optional: macOS menu bar app
```

A plugin cannot ship permission rules. For the risky-action prompts (G2: `git commit`, `git push`, `rm -rf`, package installs) and the denied commands (secret files, `--no-verify`, `git push --force`), merge the `ask` and `deny` lists of `plugins/my-agent/l4-tools-guards/permissions/permissions.json` into `permissions` in `~/.claude/settings.json` by hand. Without them those actions are not asked or blocked.

When you enable the plugin, Claude Code asks for two settings. The first is the data folder (default `~/dev/log/my-agent`; change it later in `/config`). It holds everything my-agent keeps outside task folders: the project list (`projects.txt`), the run index (`active-index.json`), the monitor state, log and settings, the price override, the improvement list (`feedback.md`) and the retrospective report copies (`gate-report/`). A leading `~` is expanded. Nothing is written into the plugin's own folder. If the folder is changed, the old one is left as is and the new one is used from then on. If the setting is missing (for example with `--plugin-dir`), `~/dev/log/my-agent` is used. The environment variables `MA_TASKS_DIR` (data folder), `MA_PROJECTS_FILE`, `MA_FEEDBACK_FILE` and `MA_GATE_REPORT_DIR` win over the setting. A folder from an earlier version (`~/my-agent`) is not moved: move it to the new place, or set the Data folder to the old path. The second setting, `task_dir`, is the task folder inside the task location (default `.my-agent`; change it later in `/config`). Task records were kept in `docs/agent` in earlier versions: they are not moved or read unless you set `task_dir` to `docs/agent` (or move the folder: `mv docs/agent .my-agent`). It must be a relative path without `..`; otherwise the default is used. The environment variable `MA_TASK_DIR` wins over the setting.

Optionally, the data folder can hold `agent-models.json`, which defines named model presets per profile (a model and an effort per agent; copy `plugins/my-agent/docs/agent-models.example.json` to start). With two or more presets for the profile, my-agent asks which one to use at the start of a task. A preset may also mark a role `"model": "inline"` (the shipped `inline` preset does so for all nine roles); the main session then runs that role itself instead of starting an agent, on both hosts. Without the file nothing changes: every agent runs on the model and effort of its definition file.

## Use in Codex

my-agent also runs in Codex. Only a local clone of this repository was tried as the marketplace source:

```bash
git clone https://github.com/minpple/my-plugins ~/dev/my-plugins
codex plugin marketplace add ~/dev/my-plugins
codex plugin add my-agent@my-plugins
```

- Codex does not run a plugin's hooks until you trust them. Start Codex once; on the `Hooks need review` screen, trust the my-agent hooks (`t` trusts all). Before that, Intake names the hooks that did not run.
- Codex lists the main skill as `my-agent:my-agent`, beside `my-agent:monitor`, from `skills/my-agent/SKILL.md`. At session start the my-agent hook gives Codex one line with the plugin, data and task folders.
- Codex loads agent definitions from `~/.codex/agents/`, not from the plugin. Intake installs the nine my-agent roles there as `my-agent-<role>`, so Codex runs subagents as my-agent roles. Until they are installed, Codex refuses the names, and the subagent start and stop records and the role-based checks do not apply.
- At the start of a task Intake checks the nine my-agent agents in `~/.codex/agents/` and, when they are missing or stale, asks before installing them (`build-codex.py --install-agents`). A file without the my-agent version comment is never overwritten. New agents show in a new Codex session.
- `/my-agent:monitor` is the skill `my-agent:monitor` in Codex, and Codex lists it.
- Codex differs in some places: no coder worktree, no background start, and the plugin settings are not passed. Codex has no G2 permission dialog of its own: a risky action stops the call, my-agent asks in its own popup, and after `Allow once` it lets that one call through. Model presets apply on Codex through the `codex` section of `agent-models.json`; agent `tools` and `maxTurns` are not available. `plugins/my-agent/l1-orchestration/hosts.md` maps each name, and section 4.14 of `plugins/my-agent/docs/build-guide/my-agent-architecture.md` lists the limits.

## my-agent

The main session (L1) takes a request, runs plan → execute → verify → review in order, and asks the person in a popup at fixed points.

| Level | Members |
|---|---|
| L1 | Main session (`/my-agent` skill): runs the steps, delegates, asks, records |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: plans, judgments, decision analysis |
| L3 | `explorer` · `researcher` · `writer` · `coder`: one assigned piece of work each |
| L4 | Tools·MCP · hooks · permission rules · scripts: running, recording and blocking |

The whole architecture — each level's components, their roles and permissions, the steps and gates, and the format of every task file — is on one page, `docs/architecture.html`, published as [architecture](https://minpple.github.io/my-plugins/architecture.html). The site root, [introduction](https://minpple.github.io/my-plugins/), shows the feature overview. `python3 tools/build-docs.py` builds the architecture page from the plugin files; run it again after changing them.

| Command | What it does |
|---|---|
| `/my-agent <request>` | Starts a new task. |
| `/my-agent --auto <request>` | Starts a new task and lets the main session answer the routine popups; the final acceptance (G3) and escalations still go to you. Combine with a profile flag if you like. |
| `/my-agent --dev <request>` | Starts a new task with the profile you name: `--general`, `--research` or `--dev`. Without a flag, the profile is picked from the request. |
| `/my-agent continue` | Continues the task in progress. |
| `/my-agent status` | Shows the task in progress and recent tasks. |
| `/my-agent:monitor` | Opens a local, read-only web page of task records, with a Report tab that sums up the scope, plan and results of the selected task on one page. Also `status`, `stop`. |

Task records are kept in `<task location>/<task_dir>/<task ID>/` (by default `.my-agent/<task ID>/`).
Finished tasks pile up there and in the monitor's list. To move tasks finished 30 days ago or more to `<task_dir>/.archived/` (out of the list; move a folder back to bring it back):

```bash
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py --dry-run [--data-dir <folder>] [--task-dir <folder>]   # list only
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py [--days N] [--data-dir <folder>] [--task-dir <folder>]
```

Run by hand in a shell, the script does not know the setting. Unless your data folder is the default `~/dev/log/my-agent`, pass it with `--data-dir <folder>` so the script finds the project list; likewise pass `--task-dir <folder>` if you changed `task_dir`.

## Update and remove

```bash
claude plugin marketplace update my-plugins
claude plugin update my-agent@my-plugins
claude plugin uninstall my-agent@my-plugins
claude plugin update my-agent-tray@my-plugins      # if installed
claude plugin uninstall my-agent-tray@my-plugins   # if installed
```

## Repository layout

- `CLAUDE.md`: notes for development (folder roles, test commands, version rule)
- `.claude-plugin/marketplace.json`: plugin list
- `.agents/plugins/marketplace.json`: plugin list for Codex
- `plugins/<name>/`: a plugin. Only this folder is copied on install.
- `tools/build-docs.py`, `tools/docs-template.html`: build the my-agent architecture page
- `docs/architecture.html`: the architecture page (generated; GitHub Pages source `main` · `/docs`)
- `docs/index.html`: the my-agent feature overview in English (the site root; maintained by hand)
- `docs/index-ko.html`: the my-agent feature overview in Korean (maintained by hand)
- `tests/`: tests for `tools/`
- `docs/handoff/`: handoff notes for work continued in another environment
- `.my-agent/`: my-agent task records from this repository. Excluded from git.
- `plugins/my-agent/docs/reference.md`: sources of the reference documents. The local copies in `plugins/my-agent/docs/ref/` are excluded from git.

## License

[MIT](LICENSE)
