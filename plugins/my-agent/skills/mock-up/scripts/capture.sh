#!/bin/sh
# Capture a mockup HTML to PNG with headless Chrome.
# Usage: capture.sh <index.html> [--scale N]
# Size comes from <meta name="mockup-size" content="WxH"> (default 1440x900 when the meta is missing).
# Output: <name>.png next to the HTML. Override the browser with CHROME_BIN.
# The PNG shows the settled final state: the page is opened with ?capture=1 (the canvas boot
# script sets data-capture on <html>) and Chrome gets --force-prefers-reduced-motion.

usage() { echo "usage: capture.sh <file.html> [--scale N]" >&2; exit 1; }

SCALE=2
HTML=""
while [ $# -gt 0 ]; do
  case "$1" in
    --scale)
      [ $# -ge 2 ] || usage
      SCALE="$2"; shift 2 ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *)
      [ -z "$HTML" ] || { echo "only one HTML file is allowed" >&2; usage; }
      HTML="$1"; shift ;;
  esac
done
case "$SCALE" in ''|*[!0-9]*) echo "--scale must be a positive integer" >&2; exit 1 ;; esac
[ "$SCALE" -ge 1 ] || { echo "--scale must be a positive integer" >&2; exit 1; }
[ -n "$HTML" ] && [ -f "$HTML" ] || usage

# Find a Chromium-based browser.
CHROME="${CHROME_BIN:-}"
if [ -z "$CHROME" ]; then
  for c in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
    [ -x "$c" ] && { CHROME="$c"; break; }
  done
fi
if [ -z "$CHROME" ]; then
  for c in google-chrome chromium chromium-browser; do
    command -v "$c" >/dev/null 2>&1 && { CHROME=$(command -v "$c"); break; }
  done
fi
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  echo "no Chromium-based browser found: install Google Chrome or set CHROME_BIN" >&2
  exit 1
fi

# Read the size from the meta tag; warn and fall back when it is missing or malformed.
SIZE=$(tr '\n' ' ' < "$HTML" \
  | sed -n "s/.*<meta[^>]*name=[\"']mockup-size[\"'][^>]*content=[\"'] *\([0-9][0-9]*\) *[x×] *\([0-9][0-9]*\) *[\"'].*/\1x\2/p")
if [ -z "$SIZE" ]; then
  echo "warning: no valid <meta name=\"mockup-size\" content=\"WxH\"> found; using 1440x900" >&2
  SIZE="1440x900"
fi
W=${SIZE%x*}
H=${SIZE#*x}

# Warn (stderr only; exit code and output line unchanged) when an animated mockup lacks the boot script.
if grep -q -e '@keyframes' -e 'fx-' "$HTML" && ! grep -q 'data-capture' "$HTML"; then
  echo "warning: the HTML has animation (@keyframes or fx-) but no data-capture boot script; animated state may not settle. Copy the boot script from templates/canvas.html" >&2
fi

DIR=$(cd "$(dirname "$HTML")" && pwd)
BASE=$(basename "$HTML")
OUT="$DIR/${BASE%.html}.png"
# Escape the path first, then append the query string (it must not go through the escaping).
URL="file://$(printf '%s' "$DIR/$BASE" | sed 's/%/%25/g; s/ /%20/g; s/#/%23/g; s/?/%3F/g')?capture=1"

PROFILE=$(mktemp -d)
LOG=$(mktemp)
trap 'rm -rf "$PROFILE" "$LOG"' EXIT

# Remove any previous PNG so a failed capture can never look like a success.
rm -f "$OUT"

# ?capture=1 is the guaranteed path to the settled state; --force-prefers-reduced-motion is a second path.
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
  --user-data-dir="$PROFILE" \
  --force-device-scale-factor="$SCALE" \
  --force-prefers-reduced-motion \
  --window-size="$W,$H" \
  --virtual-time-budget=3000 \
  --screenshot="$OUT" "$URL" >"$LOG" 2>&1 &
PID=$!

# Watchdog: kill Chrome after 60 s. Its output goes to /dev/null so the orphaned sleep
# never holds the caller's stdout/stderr open (a caller reading through a pipe must not hang).
( sleep 60; kill "$PID" 2>/dev/null ) >/dev/null 2>&1 &
WD=$!
wait "$PID" 2>/dev/null
# Stop the sleep child first, then the watchdog subshell.
pkill -P "$WD" 2>/dev/null
kill "$WD" 2>/dev/null
wait "$WD" 2>/dev/null

if [ ! -s "$OUT" ]; then
  echo "capture failed: $OUT was not created" >&2
  tail -n 10 "$LOG" >&2
  exit 1
fi

# Verify the output size (sips is macOS-only; skipped elsewhere).
EXPECT_W=$((W * SCALE)); EXPECT_H=$((H * SCALE))
if command -v sips >/dev/null 2>&1; then
  GOT_W=$(sips -g pixelWidth "$OUT" 2>/dev/null | awk '/pixelWidth/{print $2}')
  GOT_H=$(sips -g pixelHeight "$OUT" 2>/dev/null | awk '/pixelHeight/{print $2}')
  if [ "$GOT_W" != "$EXPECT_W" ] || [ "$GOT_H" != "$EXPECT_H" ]; then
    echo "warning: PNG is ${GOT_W}x${GOT_H}, expected ${EXPECT_W}x${EXPECT_H}" >&2
  fi
fi
echo "$OUT (${W}x${H} @${SCALE}x)"
