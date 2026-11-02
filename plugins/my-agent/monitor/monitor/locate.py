"""The one comparison that decides whether a /api/health answer is this monitor (monitor-up.py and open-html.py)."""

APP = 'my-agent-monitor'


def is_ours(health_json, root) -> bool:
    """True when the health JSON names this app and this monitor folder; anything else (None included) is False."""
    return isinstance(health_json, dict) and health_json.get('app') == APP and health_json.get('root') == str(root)
