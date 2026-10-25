"""How monitor-up.py opens the monitor: a new window where the default browser allows it, else a tab (macOS only)."""
import json
import plistlib
import subprocess
from pathlib import Path

LS_PLIST = Path.home() / 'Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist'
SAFARI = 'com.apple.safari'
CHROME = 'com.google.chrome'
BROWSERS = ('default', 'safari', 'chrome')
CHROMIUM = frozenset({
    'com.google.chrome', 'com.google.chrome.beta', 'com.google.chrome.dev', 'com.google.chrome.canary',
    'com.microsoft.edgemac', 'com.microsoft.edgemac.beta', 'com.microsoft.edgemac.dev', 'com.microsoft.edgemac.canary',
    'com.brave.browser', 'com.brave.browser.beta', 'com.brave.browser.nightly',
    'org.chromium.chromium', 'com.vivaldi.vivaldi',
})
SAFARI_SCRIPT = '''on run argv
  tell application "Safari"
    make new document with properties {URL:item 1 of argv}
    set bounds of front window to {80, 60, 1280, 860}
    activate
  end tell
end run'''
_DETECT = object()


def read_mode(tasks_dir) -> str:
    """'tab' only when monitor-config.json says {"open": "tab"}; anything else (missing, broken, unknown value) is 'window'."""
    try:
        data = json.loads((Path(tasks_dir) / 'monitor-config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'window'
    return 'tab' if isinstance(data, dict) and data.get('open') == 'tab' else 'window'


def read_browser(tasks_dir) -> str:
    """The `browser` key of monitor-config.json ('safari' | 'chrome'); anything else (missing, broken, unknown) is 'default'."""
    try:
        data = json.loads((Path(tasks_dir) / 'monitor-config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'default'
    value = data.get('browser') if isinstance(data, dict) else None
    return value if value in BROWSERS else 'default'


def write_browser(tasks_dir, value) -> bool:
    """Set only the `browser` key of monitor-config.json (other keys kept; folder and file created when missing)."""
    if value not in BROWSERS:
        return False
    path = Path(tasks_dir) / 'monitor-config.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    data['browser'] = value
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
    except OSError:
        return False
    return True


def default_browser(plist_path=None):
    """Lower-case bundle id of the http handler; Safari when the plist has none; None when it cannot be read."""
    try:
        with open(plist_path or LS_PLIST, 'rb') as f:
            data = plistlib.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    handlers = data.get('LSHandlers')
    for h in handlers if isinstance(handlers, list) else []:
        if isinstance(h, dict) and h.get('LSHandlerURLScheme') == 'http':
            role = h.get('LSHandlerRoleAll')
            return role.lower() if isinstance(role, str) else None
    return SAFARI


def kind(bundle_id) -> str:
    if bundle_id == SAFARI:
        return 'safari'
    return 'chromium' if bundle_id in CHROMIUM else 'other'


def commands(url, mode, bundle_id, browser='default'):
    """(method, argv) pairs to try in order; the last is always the plain tab in the default browser."""
    tab = ('tab', ['open', url])
    if browser == 'safari':
        first = ('window', ['osascript', '-e', SAFARI_SCRIPT, url]) if mode != 'tab' else ('tab', ['open', '-a', 'Safari', url])
        return [first, tab]
    if browser == 'chrome':
        first = (('window', ['open', '-n', '-b', CHROME, '--args', f'--app={url}', '--window-size=1200,800'])
                 if mode != 'tab' else ('tab', ['open', '-b', CHROME, url]))
        return [first, tab]
    if mode == 'tab':
        return [tab]
    k = kind(bundle_id)
    if k == 'chromium':
        return [('window', ['open', '-n', '-b', bundle_id, '--args', f'--app={url}', '--window-size=1200,800']), tab]
    if k == 'safari':
        return [('window', ['osascript', '-e', SAFARI_SCRIPT, url]), tab]
    return [tab]


def open_monitor(url, mode, run=subprocess.run, bundle_id=_DETECT, browser='default') -> str:
    """Open url; return 'window', 'tab' or 'failed'. Never raises: the monitor must not stop my-agent."""
    try:
        if bundle_id is _DETECT and browser not in ('safari', 'chrome'):
            bundle_id = default_browser()
        for method, argv in commands(url, mode, bundle_id, browser):
            try:
                r = run(argv, check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode == 0:
                    return method
            except Exception:
                continue
    except Exception:
        pass
    return 'failed'
