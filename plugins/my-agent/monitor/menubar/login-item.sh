#!/bin/sh
# Register / unregister the menu bar app as a login item (launchd user agent).
# install and uninstall write outside the repository (~/Library/LaunchAgents).
here=$(cd "$(dirname "$0")" && pwd)
bin="$here/build/my-agent-menubar"
label="my-agent.monitor-menubar"
plist="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"

case "$1" in
  install)
    if [ ! -x "$bin" ]; then
      echo "not installed: build first (sh menubar/build.sh)"
      exit 1
    fi
    mkdir -p "$HOME/Library/LaunchAgents"
    xbin=$(printf '%s' "$bin" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')
    cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
    <string>$xbin</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict></plist>
PLIST
    launchctl bootout "$domain/$label" >/dev/null 2>&1
    if launchctl bootstrap "$domain" "$plist"; then
      echo "installed: ~/Library/LaunchAgents/$label.plist (loaded)"
    else
      echo "not loaded: launchctl bootstrap failed; run login-item.sh uninstall"
      exit 1
    fi
    ;;
  uninstall)
    launchctl bootout "$domain/$label" >/dev/null 2>&1
    if [ -e "$plist" ]; then
      rm -f "$plist"
      echo "removed: ~/Library/LaunchAgents/$label.plist"
    else
      echo "nothing to remove: ~/Library/LaunchAgents/$label.plist"
    fi
    ;;
  status)
    if launchctl print "$domain/$label" >/dev/null 2>&1; then
      echo "login item: loaded ($label)"
    else
      echo "login item: not loaded ($label)"
    fi
    ;;
  *)
    echo "usage: login-item.sh install|uninstall|status"
    exit 2
    ;;
esac
