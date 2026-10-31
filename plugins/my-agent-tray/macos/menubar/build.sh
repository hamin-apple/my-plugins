#!/bin/sh
# Build the menu bar app with the system swiftc. Writes only under macos/menubar/build/.
here=$(cd "$(dirname "$0")" && pwd)
out="$here/build"

if ! /usr/bin/swiftc -version >/dev/null 2>&1; then
  echo "build failed: /usr/bin/swiftc did not run (install Command Line Tools: xcode-select --install)"
  exit 1
fi
py=$(command -v python3)
if [ -z "$py" ]; then
  echo "build failed: python3 not found in PATH"
  exit 1
fi

mkdir -p "$out/module-cache" || { echo "build failed: cannot create $out"; exit 1; }
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
{
  printf 'let pythonPath = "%s"\n' "$(esc "$py")"
} > "$out/Config.swift"

if ! log=$(cd "$here" && /usr/bin/swiftc -O -module-cache-path build/module-cache -o build/my-agent-menubar Sources/*.swift build/Config.swift 2>&1); then
  echo "build failed: $(printf '%s\n' "$log" | grep -m1 'error' || printf '%s\n' "$log" | head -n 1)"
  exit 1
fi
echo "built: $out/my-agent-menubar"
