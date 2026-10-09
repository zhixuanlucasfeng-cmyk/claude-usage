#!/bin/sh
# Claude Code status line: show plan usage, and save rate_limits for the
# claude-usage desktop widget (Claude Code keeps them in memory only).
in=$(cat)
dir="$HOME/Library/Application Support/ClaudeUsageWidget"
mkdir -p "$dir"
if printf '%s' "$in" | jq -e '.rate_limits' >/dev/null 2>&1; then
  printf '%s' "$in" | jq -c '{rate_limits, saved_at: (now | floor)}' > "$dir/claude-limits.tmp" \
    && mv "$dir/claude-limits.tmp" "$dir/claude-limits.json"
fi
printf '%s' "$in" | jq -r '
  def pct(w): if w.used_percentage == null then empty else "\(w.used_percentage | floor)%" end;
  [ (.model.display_name // empty),
    (.rate_limits.five_hour | select(. != null) | "5小时 " + pct(.)),
    (.rate_limits.seven_day | select(. != null) | "本周 " + pct(.)) ] | join("  ·  ")'
