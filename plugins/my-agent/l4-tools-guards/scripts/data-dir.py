#!/usr/bin/env python3
"""Print the resolved my-agent data folder (absolute path, one line).

usage: data-dir.py [--data-dir X]
X is the `data_dir` setting. $MA_TASKS_DIR wins over it; an empty X or an unsubstituted `${...}` placeholder means
"not set" and gives ~/dev/my-agent. Exit 0.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='print the my-agent data folder')
    parser.add_argument('--data-dir', default=None)
    args = parser.parse_args()
    print(ma_data.data_dir(args.data_dir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
