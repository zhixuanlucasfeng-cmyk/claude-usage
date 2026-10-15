"""Data for the desktop widget: today per tool, Codex weekly limit, last 7 days,
plus the permanent daily history file."""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from claude_usage.pricing import cost_for_tokens
from claude_usage.scanner import UsageRecord
from claude_usage.sources import CodexScan, TokenEvent

SOURCES = ("claude", "codex", "deepseek")
POWER_ENGINES = ("claude", "codex", "deepseek", "opencode")


def _claude_tokens(r: UsageRecord) -> int:
    return r.input_tokens + r.output_tokens + r.cache_creation_input_tokens + r.cache_read_input_tokens


def _claude_cost(r: UsageRecord) -> float:
    return cost_for_tokens(
        r.model, r.input_tokens, r.output_tokens,
        r.cache_creation_input_tokens, r.cache_read_input_tokens,
    ) or 0.0


def _under(cwd: str, power_dir: Path) -> bool:
    return bool(cwd) and (Path(cwd) == power_dir or power_dir in Path(cwd).parents)


def daily_totals(claude: list[UsageRecord], events: list[TokenEvent]) -> dict[date, dict]:
    """Tokens per local calendar day per tool, plus Claude's dollar cost."""
    days: dict[date, dict] = {}

    def row(ts: datetime) -> dict:
        return days.setdefault(ts.astimezone().date(), {**dict.fromkeys(SOURCES, 0), "claude_cost": 0.0})

    for r in claude:
        t = row(r.timestamp)
        t["claude"] += _claude_tokens(r)
        t["claude_cost"] += _claude_cost(r)
    for e in events:
        row(e.timestamp)[e.source] += e.tokens
    return days


def build_widget_data(
    claude: list[UsageRecord], codex: CodexScan, hermes: list[TokenEvent], today: date,
    power_dir: Path = Path.home() / ".power",
    power_sessions: set[str] = frozenset(),
    opencode: list[TokenEvent] = (),
) -> dict:
    """Days are the viewer's local calendar days, not UTC."""
    totals = daily_totals(claude, [*codex.events, *hermes])
    empty = {**dict.fromkeys(SOURCES, 0), "claude_cost": 0.0}
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    t = totals.get(today, empty)

    limit = None
    if codex.limit:
        limit = {
            "used_percent": codex.limit.used_percent,
            "resets_at": codex.limit.resets_at.isoformat(),
        }
    # Power runs its Claude crew with cwd = ~/.power; its other engines are matched
    # by the session ids Power logs (~/.power/sessions.jsonl). opencode is only
    # scanned for Power's sessions, so all of it counts.
    power: dict[date, dict] = {}

    def prow(ts: datetime) -> dict:
        return power.setdefault(ts.astimezone().date(), {"tokens": 0, "cost": 0.0, **dict.fromkeys(POWER_ENGINES, 0)})

    for r in claude:
        if _under(r.cwd, power_dir):
            p = prow(r.timestamp)
            p["tokens"] += _claude_tokens(r)
            p["claude"] += _claude_tokens(r)
            p["cost"] += _claude_cost(r)  # Claude part only; the others report no price
    for e in [*codex.events, *hermes, *opencode]:
        if e.source == "opencode" or e.session in power_sessions or _under(e.cwd, power_dir):
            p = prow(e.timestamp)
            p["tokens"] += e.tokens
            p[e.source] += e.tokens
    pt = power.get(today, {"tokens": 0, "cost": 0.0})
    return {
        # Overlaps the per-tool totals below: it is Power's share of them.
        "power": {"tokens": pt["tokens"], "cost": round(pt["cost"], 2)},
        # Every day Power was used, for the dashboard's Power card.
        "power_daily": [{"d": d.isoformat(), **v, "cost": round(v["cost"], 4)} for d, v in sorted(power.items())],
        "today": {**{s: t[s] for s in SOURCES}, "claude_cost": round(t["claude_cost"], 2)},
        "codex_limit": limit,
        "week": [{"d": d.isoformat(), **{s: totals.get(d, empty)[s] for s in SOURCES},
                  "power": power.get(d, {"tokens": 0})["tokens"]} for d in days],
    }


HISTORY_FIELDS = ("date", *SOURCES, "claude_cost")


def save_history(path: Path, totals: dict[date, dict]) -> None:
    """Keep every day's usage in a CSV, so it outlives the tools' own logs.

    Claude Code deletes old transcripts, so a saved day only ever grows:
    partly cleaned logs never shrink it, and days gone from the logs stay.
    """
    rows: dict[str, dict] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            rows = {r["date"]: r for r in csv.DictReader(f)}
    for d, t in totals.items():
        old = rows.get(d.isoformat(), {})
        rows[d.isoformat()] = {
            "date": d.isoformat(),
            **{s: max(t[s], int(float(old.get(s) or 0))) for s in SOURCES},
            "claude_cost": f"{max(t['claude_cost'], float(old.get('claude_cost') or 0)):.2f}",
        }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, HISTORY_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows[k] for k in sorted(rows))
    text = buf.getvalue()
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written history


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
