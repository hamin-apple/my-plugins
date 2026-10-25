"""permissions/permissions.json: the G2 ask/deny list (architecture 4.4 "G2에서 묻는 행동", 4.12 비밀값 차단).

Live run: `git -C <repo> commit` did not match `Bash(git commit:*)` and committed without the G2 ask."""
import json
import unittest

from helpers import L4

ASK = [
    'Bash(git commit:*)', 'Bash(git push:*)', 'Bash(git * commit*)', 'Bash(git * push*)', 'Bash(rm -rf:*)',
    'Bash(npm i:*)', 'Bash(npm install:*)', 'Bash(pip install:*)', 'Bash(pip3 install:*)', 'Bash(brew install:*)',
    'mcp__plugin_slack_slack__slack_send_message', 'mcp__plugin_slack_slack__slack_schedule_message',
    'mcp__plugin_github_github__create_pull_request', 'mcp__plugin_github_github__create_or_update_file',
    'mcp__plugin_github_github__push_files', 'mcp__plugin_vercel_vercel__create_deployment',
]
DENY = [
    'Bash(git push --force*)', 'Bash(git push * --force*)', 'Bash(git push -f*)', 'Bash(git push * -f*)',
    'Bash(git * push --force*)', 'Bash(git * push * --force*)', 'Bash(git * push -f*)', 'Bash(git * push * -f*)',
    'Bash(*--no-verify*)',
    'Read(//**/.env)', 'Read(//**/.env.*)', 'Read(//**/*.pem)', 'Read(//**/*.key)',
    'Read(~/.ssh/**)', 'Read(~/.aws/**)', 'Read(~/.config/gh/**)', 'Read(~/.netrc)',
]


class PermissionsTest(unittest.TestCase):
    def test_lists(self):
        data = json.loads((L4 / 'permissions' / 'permissions.json').read_text(encoding='utf-8'))
        self.assertEqual(set(data), {'permissions'})
        self.assertEqual(data['permissions'], {'ask': ASK, 'deny': DENY})


if __name__ == '__main__':
    unittest.main()
