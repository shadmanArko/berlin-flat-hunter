#!/bin/sh
PLIST="$HOME/Library/LaunchAgents/com.flathunter.watcher.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "watcher stopped and removed"
