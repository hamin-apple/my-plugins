#!/usr/bin/env bash
# Judge check (architecture 4.13 "judge checks"): run my-agent:verifier on each fixture note and compare the first
# line of the verify.md it writes with expected.json. Paid (one verifier run per note, capped by --max-budget-usd);
# run it by hand after changing verifier.md or reviewer.md. Each note gets its own throwaway git project with a
# docs/agent/.active, so scope-guard applies exactly as in a real task.
# usage: run-judge-check.sh [note.md ...]   (default: every note in expected.json)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/judge-XXXXXX")"
TASK=261025-judge
NOTES=("$@")
[ ${#NOTES[@]} -gt 0 ] || read -r -a NOTES <<< "$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))))' "$HERE/expected.json")"
fail=0
for note in "${NOTES[@]}"; do
  want=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$HERE/expected.json" "$note")
  proj="$WORK/${note%.md}"
  T="$proj/docs/agent/$TASK"
  mkdir -p "$T/work"
  git init -q "$proj"
  printf 'task: %s\nphase: 4\nsession: judge\nstarted: 2026-10-25 00:00\n' "$TASK" > "$proj/docs/agent/.active"
  printf 'Status: active\nProfile: research\nTask: %s\nRequest: shlex summary note\n' "$TASK" > "$T/intake.md"
  cp "$HERE/scope.md" "$T/scope.md"
  printf '# Plan\n\n## Approval\n\n- Approved 2026-10-25 09:30 G1b\n' > "$T/plan.md"   # Verify runs after G1b
  cp "$HERE/$note" "$T/work/final.md"
  prompt="Call the agent my-agent:verifier exactly once with exactly this prompt, wait for it, then print the first line of $T/verify.md and stop. This is a judge test: do not invoke any skill (no /my-agent continue).

Completion criteria file: $T/scope.md
Scope change: none
Deliverable: $T/work/final.md
intake: $T/intake.md
Result path: $T/verify.md"
  (cd "$proj" && printf '%s\n' "$prompt" | claude -p --plugin-dir "$PLUGIN" --model haiku --max-budget-usd 2 \
      --permission-mode acceptEdits --allowedTools Agent Read Grep Glob Write WebFetch \
      > "$proj/run.out" 2> "$proj/run.err")
  got=$(head -1 "$T/verify.md" 2>/dev/null | sed 's/^Verdict: //; s/^ALL //')
  if [ "$got" = "$want" ]; then
    echo "ok   $note: $want"
  else
    echo "MISS $note: want $want, got '${got:-no verify.md}' (see $proj)"
    fail=1
  fi
done
if [ $fail -eq 0 ]; then
  echo "JUDGE OK"
  rm -rf "$WORK"
else
  echo "JUDGE MISMATCH (kept $WORK)"
fi
exit $fail
