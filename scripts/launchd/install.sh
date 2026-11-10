#!/bin/sh
# Installs a macOS LaunchAgent: starts the watcher at login, restarts it if it crashes,
# and keeps the Mac from idle-sleeping while it runs (caffeinate). Costs nothing.
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UV="$(command -v uv)"
LABEL="com.flathunter.watcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$UV</string><string>run</string><string>python</string>
    <string>-m</string><string>flathunter.ops.main</string><string>watch</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/watcher.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/watcher.log</string>
</dict></plist>
PLISTEOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "installed and started: $LABEL (logs: $ROOT/logs/watcher.log)"
