#!/bin/sh
# §6 step 0 probe runs (plan Task 9). Run from anywhere; works in ~/dev/labs/my-agent-sandbox.
# usage: run-probes.sh [r1 r2 ...]   (default: all)
set -u
S="$HOME/dev/labs/my-agent-sandbox"
PLUGIN="$HOME/dev/my-plugins/plugins/my-agent"
cd "$S" 2>/dev/null || [ "${1:-}" = r11 ] || exit 1   # r11 does not need the sandbox
[ "$(pwd)" = "$S" ] && mkdir -p .probe
TOOLS='Agent Read Bash(pwd) Bash(pwd:*) Bash(sleep:*) Bash(echo:*) Bash(date:*) Bash(ls:*)'

run() {  # run <name> <permission-mode> <prompt>
  name=$1; mode=$2; prompt=$3
  echo "== $name"
  claude -p --plugin-dir "$PLUGIN" --model haiku --permission-mode "$mode" --max-budget-usd 1 \
    --allowedTools $TOOLS --output-format stream-json --verbose "$prompt" > ".probe/run-$name.json" 2> ".probe/run-$name.err"
  echo "   exit $? · $(wc -l < ".probe/run-$name.json") events"
}

want() { [ $# -eq 0 ] && return 0; for x in $ALL; do [ "$x" = "$1" ] && return 0; done; return 1; }
ALL="${*:-r1 r2 r3 r4 r5 r6 r7}"   # r10 (workflow) and r11 only when named: r10 needs the user's OK, r11 installs a plugin

# r11: does an INSTALLED plugin's skill get the data_dir setting (A: skill frontmatter hook env CLAUDE_PLUGIN_OPTION_DATA_DIR, A2: same from the plugin's hooks/hooks.json,
# A3: ${user_config.data_dir} substituted inside the skill hook's command string,
# B: ${user_config.data_dir} substituted in the SKILL.md body)? Uses an isolated CLAUDE_CONFIG_DIR and a
# directory marketplace built from data-dir-skill/SKILL.md; never touches ~/.claude*. Needs a login in the
# isolated dir (or ANTHROPIC_API_KEY); prints NOT RUN lines when it cannot run.
# Set R11_HOME to reuse a base dir (default: a new mktemp dir); R11_VALUE to change the setting value.
r11() {
  base=${R11_HOME:-$(mktemp -d)}; val=${R11_VALUE:-$base/chosen-data-dir}
  cfg="$base/config"; mp="$base/mp"; out="$base/probe-out"
  rm -rf "$mp" "$out"; mkdir -p "$cfg" "$mp/.claude-plugin" "$mp/dd/.claude-plugin" "$mp/dd/skills/data-dir-probe" "$mp/dd/hooks" "$out"
  cp "$PLUGIN/tests/probe/data-dir-skill/SKILL.md" "$mp/dd/skills/data-dir-probe/SKILL.md"
  cat > "$mp/dd/.claude-plugin/plugin.json" <<'JSON'
{"name":"data-dir-probe","version":"0.0.1","description":"r11 probe","hooks":"./hooks/hooks.json",
 "userConfig":{"data_dir":{"type":"directory","title":"Data folder","description":"probe","required":true,"default":"~/my-agent"}}}
JSON
  cat > "$mp/dd/hooks/hooks.json" <<'JSON'
{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"python3 \"$PROBE_LOG\" plugin-data-dir \"$CLAUDE_PLUGIN_OPTION_DATA_DIR\"","timeout":10}]}]}}
JSON
  cat > "$mp/.claude-plugin/marketplace.json" <<'JSON'
{"name":"r11-mp","owner":{"name":"probe"},"plugins":[{"name":"data-dir-probe","source":"./dd","description":"r11"}]}
JSON
  echo "== r11 (base $base)"
  export CLAUDE_CONFIG_DIR="$cfg" PROBE_OUT_DIR="$out" PROBE_LOG="$PLUGIN/tests/probe/probe-log.py"
  claude plugin marketplace add "$mp" > "$base/install.log" 2>&1 &&
    claude plugin install data-dir-probe@r11-mp --config "data_dir=$val" >> "$base/install.log" 2>&1 ||
    { echo "   install failed, see $base/install.log"; return 1; }
  claude -p --model haiku --permission-mode default --max-budget-usd 1 --allowedTools 'Skill Bash(echo:*)' \
    --output-format stream-json --verbose '/data-dir-probe:data-dir-probe' > "$base/run-r11.json" 2> "$base/run-r11.err"
  rc=$?
  echo "   exit $rc · setting=$val"
  [ "$rc" -eq 0 ] || { echo "   NOT RUN (claude failed):"; head -c 400 "$base/run-r11.err"; grep -o '"text":"[^"]*"' "$base/run-r11.json" | head -n 2; }
  echo "   A (hook env):"; cat "$out/skill-data-dir.jsonl" 2>/dev/null || echo "   (no hook log)"
  echo "   A2 (plugin hooks.json env):"; cat "$out/plugin-data-dir.jsonl" 2>/dev/null || echo "   (no hook log)"
  echo "   A3 (skill hook placeholder):"; cat "$out/skill-placeholder.jsonl" 2>/dev/null || echo "   (no hook log)"
  # installed copy check: find the installed SKILL.md under $cfg (cache) or $mp (directory marketplace plugins load in place)
  if find "$cfg" "$mp" -name SKILL.md -type f -exec grep -l skill-placeholder {} + 2>/dev/null | grep -q .; then
    echo "   A3 hook installed: yes"
  else
    echo "   A3 hook installed: no"
  fi
  echo "   B (body):"; grep -o 'BODY=\[[^]]*\]' "$base/run-r11.json" | sort -u
}

for r in $ALL; do
  case $r in
    r1) run r1 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r1", prompt "Run: pwd". Then reply with its last line.' ;;
    r2) run r2 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r2", isolation "worktree", prompt "Run: pwd". Then reply with its last line.' ;;
    r3) run r3 default '/my-agent:probe-skill' ;;
    r4) run r4 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r4", run_in_background true, prompt "Run: sleep 45 ; then run: echo late". Do not wait for it. Immediately reply STARTED and end your turn.' ;;
    r5) run r5 default 'Reply with the single word OK.' ;;
    r6) run r6 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r6", prompt "Run: touch /tmp/ma-probe-x". Then reply with its last line.' ;;
    r10) TOOLS="$TOOLS Workflow"; run r10 default "$(cat "$PLUGIN/tests/probe/r10-prompt.txt")" ;;
    r11) r11 ;;
    r7) run r7 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r7", prompt "Run these five commands one at a time, one Bash call each: date ; pwd ; ls ; echo one ; echo two". Then reply with its last line.' ;;
  esac
done
