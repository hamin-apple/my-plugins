#!/bin/sh
# §6 step 0 probe runs (plan Task 9). Run from anywhere; works in ~/dev/labs/my-agent-sandbox.
# usage: run-probes.sh [r1 r2 ...]   (default: all)
set -u
S="$HOME/dev/labs/my-agent-sandbox"
PLUGIN="$HOME/dev/my-plugins/plugins/my-agent"
cd "$S" || exit 1
mkdir -p .probe
TOOLS='Agent Read Bash(pwd) Bash(pwd:*) Bash(sleep:*) Bash(echo:*) Bash(date:*) Bash(ls:*)'

run() {  # run <name> <permission-mode> <prompt>
  name=$1; mode=$2; prompt=$3
  echo "== $name"
  claude -p --plugin-dir "$PLUGIN" --model haiku --permission-mode "$mode" --max-budget-usd 1 \
    --allowedTools $TOOLS --output-format stream-json --verbose "$prompt" > ".probe/run-$name.json" 2> ".probe/run-$name.err"
  echo "   exit $? · $(wc -l < ".probe/run-$name.json") events"
}

want() { [ $# -eq 0 ] && return 0; for x in $ALL; do [ "$x" = "$1" ] && return 0; done; return 1; }
ALL="${*:-r1 r2 r3 r4 r5 r6 r7}"   # r10 (workflow) only when named: it needs the user's OK

for r in $ALL; do
  case $r in
    r1) run r1 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r1", prompt "Run: pwd". Then reply with its last line.' ;;
    r2) run r2 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r2", isolation "worktree", prompt "Run: pwd". Then reply with its last line.' ;;
    r3) run r3 default '/my-agent:probe-skill' ;;
    r4) run r4 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r4", run_in_background true, prompt "Run: sleep 45 ; then run: echo late". Do not wait for it. Immediately reply STARTED and end your turn.' ;;
    r5) run r5 default 'Reply with the single word OK.' ;;
    r6) run r6 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r6", prompt "Run: touch /tmp/ma-probe-x". Then reply with its last line.' ;;
    r10) TOOLS="$TOOLS Workflow"; run r10 default "$(cat "$PLUGIN/l4-tools-guards/probe/r10-prompt.txt")" ;;
    r7) run r7 default 'Call the Agent tool exactly once: subagent_type "my-agent:probe-worker", description "probe r7", prompt "Run these five commands one at a time, one Bash call each: date ; pwd ; ls ; echo one ; echo two". Then reply with its last line.' ;;
  esac
done
