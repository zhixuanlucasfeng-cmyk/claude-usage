#!/bin/sh
# Install claude-usage and the macOS desktop widget.
# Needs: macOS 13+, python3 3.10+, Xcode Command Line Tools (swiftc), jq.
# The widget runs the CLI from this folder's venv, so keep the folder where it is.
set -e
cd "$(dirname "$0")"

echo "==> Python package"
python3 -m venv venv
venv/bin/pip install -q -e .

echo "==> Widget"
widget/build.sh
APP="$HOME/Applications/Claude Usage Widget.app"
mkdir -p "$HOME/Applications"
pkill -x UsageWidget 2>/dev/null || true
rm -rf "$APP"
cp -R "widget/Claude Usage Widget.app" "$APP"

echo "==> Claude Code status line (plan limits for the widget)"
mkdir -p "$HOME/.claude/hooks"
cp widget/usage-statusline.sh "$HOME/.claude/hooks/usage-statusline.sh"
chmod +x "$HOME/.claude/hooks/usage-statusline.sh"
settings="$HOME/.claude/settings.json"
if ! command -v jq >/dev/null; then
  echo "    jq not found: skipped. Install jq, then re-run to show Claude plan limits."
elif [ -f "$settings" ] && jq -e '.statusLine' "$settings" >/dev/null; then
  echo "    You already have a statusLine in $settings; left it alone."
  echo "    To show plan limits on the widget, point it at ~/.claude/hooks/usage-statusline.sh"
else
  [ -f "$settings" ] || echo '{}' > "$settings"
  cp "$settings" "$settings.bak"
  jq '.statusLine = {type: "command", command: "~/.claude/hooks/usage-statusline.sh", refreshInterval: 60}' \
    "$settings.bak" > "$settings"
  echo "    Added statusLine to $settings (backup: settings.json.bak)"
fi

open "$APP"
echo
echo "Done. The widget is on your desktop (top-right). Right-click it for options."
echo "Start at login: System Settings > General > Login Items > + > $APP"
