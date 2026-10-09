"""Data for the desktop widget: today per tool, Codex weekly limit, last 7 days."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from claude_usage.pricing import cost_for_tokens
from claude_usage.scanner import UsageRecord
from claude_usage.sources import CodexScan, TokenEvent

SOURCES = ("claude", "codex", "deepseek")


def _claude_tokens(r: UsageRecord) -> int:
    return r.input_tokens + r.output_tokens + r.cache_creation_input_tokens + r.cache_read_input_tokens


def build_widget_data(
    claude: list[UsageRecord], codex: CodexScan, hermes: list[TokenEvent], today: date
) -> dict:
    """Days are the viewer's local calendar days, not UTC."""
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    tokens = {d: dict.fromkeys(SOURCES, 0) for d in days}
    claude_cost_today = 0.0

    for r in claude:
        d = r.timestamp.astimezone().date()
        if d in tokens:
            tokens[d]["claude"] += _claude_tokens(r)
            if d == today:
                claude_cost_today += cost_for_tokens(
                    r.model, r.input_tokens, r.output_tokens,
                    r.cache_creation_input_tokens, r.cache_read_input_tokens,
                ) or 0.0
    for e in [*codex.events, *hermes]:
        d = e.timestamp.astimezone().date()
        if d in tokens:
            tokens[d][e.source] += e.tokens

    limit = None
    if codex.limit:
        limit = {
            "used_percent": codex.limit.used_percent,
            "resets_at": codex.limit.resets_at.isoformat(),
        }
    return {
        "today": {**tokens[today], "claude_cost": round(claude_cost_today, 2)},
        "codex_limit": limit,
        "week": [{"d": d.isoformat(), **tokens[d]} for d in days],
    }


def _to_iso(value) -> str | None:
    """resets_at may arrive as epoch seconds or an ISO string."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def read_claude_limits(path: Path) -> dict | None:
    """Plan limits saved by the Claude Code status line script, if any."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    limits = saved.get("rate_limits") if isinstance(saved, dict) else None
    if not isinstance(limits, dict):
        return None
    out = {}
    for key in ("five_hour", "seven_day"):
        w = limits.get(key)
        if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
            out[key] = {"used_percent": float(w["used_percentage"]), "resets_at": _to_iso(w.get("resets_at"))}
    if not out:
        return None
    if isinstance(saved.get("saved_at"), (int, float)):
        out["saved_at"] = _to_iso(saved["saved_at"])
    return out
