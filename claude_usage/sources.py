"""Usage from tools other than Claude Code: Codex and Hermes (DeepSeek).

Neither has a published per-token price we can trust here (Codex runs on a
subscription; Hermes' own estimates are far off), so these report tokens only.
"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TokenEvent:
    timestamp: datetime  # aware, UTC
    source: str          # "codex" | "deepseek"
    model: str
    tokens: int          # input (incl. cached) + output


@dataclass
class CodexLimit:
    used_percent: float
    resets_at: datetime


@dataclass
class CodexScan:
    events: list[TokenEvent] = field(default_factory=list)
    limit: CodexLimit | None = None  # from the newest token_count event


def _parse_ts(value: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _usage_total(usage: dict) -> int:
    # input_tokens already includes cached_input_tokens in Codex logs.
    return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)


def scan_codex(codex_dir: Path) -> CodexScan:
    """Read ~/.codex/sessions/**/rollout-*.jsonl token_count events.

    Each event carries a cumulative total; Codex sometimes logs the same total
    twice, so we count the increase over the previous event, not the event.
    Rollout files are append-only, so each call only parses bytes added since
    the previous call (state kept in _codex_files).
    """
    scan = CodexScan()
    newest: tuple[datetime, CodexLimit] | None = None
    for path in sorted(codex_dir.glob("**/*.jsonl")):
        state = _codex_files.get(path)
        try:
            size = path.stat().st_size
            if state is None or size < state.offset:  # new or rewritten file
                state = _codex_files[path] = _CodexFile()
            if size > state.offset:
                _read_codex_tail(path, state)
        except OSError:
            continue
        scan.events.extend(state.events)
        if state.newest and (newest is None or state.newest[0] > newest[0]):
            newest = state.newest
    scan.limit = newest[1] if newest else None
    return scan


@dataclass
class _CodexFile:
    offset: int = 0
    model: str = "unknown"
    prev_total: int | None = None
    events: list[TokenEvent] = field(default_factory=list)
    newest: tuple[datetime, CodexLimit] | None = None


# ponytail: in-process only, so the first scan after a restart reads every
# file (~2 GB here, tens of seconds); persist offsets to disk if that hurts.
_codex_files: dict[Path, _CodexFile] = {}


def _read_codex_tail(path: Path, st: _CodexFile) -> None:
    with path.open("rb") as f:
        f.seek(st.offset)
        chunk = f.read()
    end = chunk.rfind(b"\n") + 1  # leave a half-written last line for next time
    st.offset += end
    for raw in chunk[:end].splitlines():
        # Most lines are large message bodies; skip them before parsing.
        if b'"token_count"' not in raw and b'"turn_context"' not in raw:
            continue
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(d, dict):
            continue
        payload = d.get("payload") or {}
        if d.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            st.model = payload["model"]
            continue
        if d.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        ts = _parse_ts(d.get("timestamp"))
        if ts is None:
            continue
        primary = (payload.get("rate_limits") or {}).get("primary") or {}
        if isinstance(primary.get("used_percent"), (int, float)) and primary.get("resets_at"):
            if st.newest is None or ts > st.newest[0]:
                st.newest = (ts, CodexLimit(
                    float(primary["used_percent"]),
                    datetime.fromtimestamp(primary["resets_at"], timezone.utc),
                ))
        info = payload.get("info") or {}
        if not info:
            continue
        total = _usage_total(info.get("total_token_usage") or {})
        last = _usage_total(info.get("last_token_usage") or {})
        if st.prev_total is None or total < st.prev_total:
            tokens = last  # first event in the file, or the counter restarted
        else:
            tokens = total - st.prev_total
        st.prev_total = total
        if tokens > 0:
            st.events.append(TokenEvent(ts, "codex", st.model, tokens))


def scan_hermes(state_db: Path) -> list[TokenEvent]:
    """Per-session token totals from Hermes' state.db, dated at session start.

    Only DeepSeek-billed sessions are kept: that is the provider in use here,
    and the other rows are empty test sessions.
    """
    if not state_db.exists():
        return []
    try:
        # Read-only: Hermes may be writing to it right now.
        conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=2)
        rows = conn.execute(
            "SELECT started_at, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens "
            "FROM sessions WHERE billing_provider = 'deepseek'"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    events = []
    for started, model, inp, out, cache_read, cache_write in rows:
        tokens = sum(int(v or 0) for v in (inp, out, cache_read, cache_write))
        if started and tokens:
            events.append(TokenEvent(datetime.fromtimestamp(started, timezone.utc), "deepseek", model or "deepseek", tokens))
    return events
