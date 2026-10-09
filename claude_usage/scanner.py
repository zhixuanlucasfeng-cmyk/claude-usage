import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class UsageRecord:
    timestamp: datetime
    cwd: str
    session_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


def _coerce_token_count(value: object) -> int:
    """Return value if it is a sane non-negative token count, else 0.

    Real logs occasionally carry null, strings, or floats in usage fields.
    A bad field degrades to 0 rather than discarding the whole record, which
    matches how a missing field already behaves. bool is excluded explicitly
    because bool is an int subclass in Python.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _dedup_key(data: dict, message: dict) -> str | None:
    """Stable identity for a single API call, used to dedupe across files.

    Claude Code copies prior turns into a new JSONL file when a session is
    resumed, forked, or compacted, so the same API call can appear in many
    files. The assistant message id plus the request id identify one call;
    the per-line uuid is a fallback for lines missing either of those.
    Returns None when no identity can be established (never deduped).
    """
    message_id = message.get("id")
    request_id = data.get("requestId")
    if (
        isinstance(message_id, str)
        and message_id
        and isinstance(request_id, str)
        and request_id
    ):
        return f"{message_id}:{request_id}"

    uuid = data.get("uuid")
    if isinstance(uuid, str) and uuid:
        return uuid

    return None


def _parse_line(line: str) -> tuple[UsageRecord, str | None] | None:
    """Parse one JSONL line into (record, dedup_key), or None if unusable."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    # json.loads succeeds on any JSON value (arrays, strings, null, numbers),
    # not just objects. Reject anything that is not an object up front.
    if not isinstance(data, dict):
        return None

    message = data.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    timestamp_str = data.get("timestamp")
    cwd = data.get("cwd")
    session_id = data.get("sessionId")
    model = message.get("model")
    # These must be non-empty strings: a non-string cwd/sessionId/model parses
    # fine here but blows up later in dict grouping or the pricing lookup.
    for value in (timestamp_str, cwd, session_id, model):
        if not isinstance(value, str) or not value:
            return None

    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    record = UsageRecord(
        timestamp=timestamp,
        cwd=cwd,
        session_id=session_id,
        model=model,
        input_tokens=_coerce_token_count(usage.get("input_tokens")),
        output_tokens=_coerce_token_count(usage.get("output_tokens")),
        cache_creation_input_tokens=_coerce_token_count(usage.get("cache_creation_input_tokens")),
        cache_read_input_tokens=_coerce_token_count(usage.get("cache_read_input_tokens")),
    )
    return record, _dedup_key(data, message)


def _scan_file_pairs(path: Path) -> list[tuple[UsageRecord, str | None]]:
    pairs: list[tuple[UsageRecord, str | None]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parsed = _parse_line(line)
            if parsed is not None:
                pairs.append(parsed)
    return pairs


def _usage_total(record: UsageRecord) -> int:
    """Sum all token fields to determine the 'completeness' of a usage record.

    A single API call may be written as multiple JSONL lines (one per content
    block in an assistant turn), all sharing the same dedup key. Earlier lines
    carry stub token values (typically output_tokens: 1) while the final line
    carries real values. The record with the highest total usage is the most
    complete and is the one to keep.
    """
    return (
        record.input_tokens
        + record.output_tokens
        + record.cache_creation_input_tokens
        + record.cache_read_input_tokens
    )


def scan_file(path: Path) -> list[UsageRecord]:
    """Scan a single file. No cross-file dedup, and errors propagate:
    a caller naming one specific file should see that file's failure."""
    return [record for record, _ in _scan_file_pairs(path)]


def scan_projects_dir(projects_dir: Path) -> list[UsageRecord]:
    """Scan every JSONL file under projects_dir, deduplicating API calls that
    appear in more than one file/line and skipping files that cannot be read.

    A single API call can be written as multiple JSONL lines sharing the same
    dedup key (e.g. one line per content block of an assistant turn, or a
    session resumed into a new file) — only the copy with the greatest total
    usage is kept, since earlier content-block lines carry a stub token count
    while the final one carries the real value.
    """
    records: list[UsageRecord] = []
    best_by_key: dict[str, UsageRecord] = {}
    for jsonl_path in projects_dir.rglob("*.jsonl"):
        try:
            pairs = _scan_file_pairs(jsonl_path)
        except (OSError, UnicodeDecodeError):
            # One unreadable or non-UTF-8 file must not abort the whole scan.
            continue
        for record, dedup_key in pairs:
            if dedup_key is None:
                records.append(record)
                continue
            existing = best_by_key.get(dedup_key)
            if existing is None or _usage_total(record) > _usage_total(existing):
                best_by_key[dedup_key] = record
    records.extend(best_by_key.values())
    return records
