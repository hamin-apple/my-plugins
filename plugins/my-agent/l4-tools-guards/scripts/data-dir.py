#!/usr/bin/env python3
"""Print the resolved my-agent data folder (absolute path, one line); with --task-dir, a second line: the task subfolder.

usage: data-dir.py [--data-dir X] [--task-dir Y]
X is the `data_dir` setting. $MA_TASKS_DIR wins over it; an empty X or an unsubstituted `${...}` placeholder means
"not set" and gives ~/dev/log/my-agent. Y is the `task_dir` setting; the second line is the relative task subfolder
($MA_TASK_DIR wins; unset, absolute, `..` or reserved gives .my-agent). Exit 0.
On Codex it first checks the hook marks (ma_host.hook_health): a hook that did not run for this session (not
trusted, or trust stale) is named on stderr, nothing is printed and the exit is 1. Claude: no check.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_data  # noqa: E402
import ma_host  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='print the my-agent data folder')
    parser.add_argument('--data-dir', default=None)
    parser.add_argument('--task-dir', default=None)
    args = parser.parse_args()
    if ma_host.env_host() == 'codex':
        problems = ma_host.hook_health(ma_host.session_id())
        if problems:
            print(ma_host.health_message(problems), file=sys.stderr)
            return 1
    print(ma_data.data_dir(args.data_dir))
    if args.task_dir is not None:
        print(ma_data.task_dir(args.task_dir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
