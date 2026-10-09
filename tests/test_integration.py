"""End-to-end test over a directory tree that reproduces, in miniature, every
real-world data shape that broke the tool when it was first run against a real
~/.claude/projects tree: duplicated calls from resumed sessions, dated model
IDs, <synthetic> messages, a malformed line, and an unreadable file.
"""

import json
from pathlib import Path

from claude_usage.cli import run


def _line(
    *,
    cwd: str,
    session_id: str,
    model: str,
    message_id: str,
    request_id: str,
    uuid: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    timestamp: str = "2026-08-12T10:00:00.000Z",
) -> str:
    return json.dumps({
        "timestamp": timestamp,
        "cwd": cwd,
        "sessionId": session_id,
        "requestId": request_id,
        "uuid": uuid,
        "message": {
            "id": message_id,
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
        },
    })


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


TERSE = "/Users/alice/terse"
OTHER = "/Users/alice/other"

# The one API call that a session resume copied into a second project's file.
RESUMED_CALL = dict(
    cwd=TERSE,
    session_id="resumed-session",
    model="claude-sonnet-4-6",
    message_id="msg_shared",
    request_id="req_shared",
    input_tokens=1_000_000,  # $3.00 at sonnet's $3/1M input
)


def _build_tree(tmp_path: Path) -> None:
    project_a = tmp_path / "-Users-alice-terse"
    project_a.mkdir()
    project_b = tmp_path / "-Users-alice-other"
    project_b.mkdir()

    _write_lines(project_a / "s1.jsonl", [
        _line(**RESUMED_CALL, uuid="uuid-a1"),
        # A malformed line in the middle must not cost us the lines around it.
        "[1,2,3]",
        _line(
            cwd=TERSE,
            session_id="haiku-session",
            model="claude-haiku-4-5-20251001",  # dated ID: $1.00 at $1/1M input
            message_id="msg_haiku",
            request_id="req_haiku",
            uuid="uuid-a2",
            input_tokens=1_000_000,
        ),
    ])

    # Invalid UTF-8 sitting alongside valid files.
    (project_a / "corrupt.jsonl").write_bytes(b"\xff\xfe\x00\x01\xff")

    _write_lines(project_b / "s2.jsonl", [
        # Same message id + request id as project A's first line: one call,
        # copied into a new file when the session was resumed.
        _line(**RESUMED_CALL, uuid="uuid-b1"),
        _line(
            cwd=OTHER,
            session_id="synthetic-session",
            model="<synthetic>",  # known, always $0.00
            message_id="msg_synth",
            request_id="req_synth",
            uuid="uuid-b2",
            input_tokens=5_000,
            output_tokens=5_000,
        ),
        _line(
            cwd=OTHER,
            session_id="cache-session",
            model="claude-sonnet-4-6",
            message_id="msg_cache",
            request_id="req_cache",
            uuid="uuid-b3",
            # 2M cache-read tokens at $3/1M * 0.1 = $0.60
            cache_read_input_tokens=2_000_000,
        ),
    ])


def test_end_to_end_report_over_realistic_tree(tmp_path):
    _build_tree(tmp_path)

    output = run(tmp_path, days=None, top_n=10)

    # Dedup: the resumed call is billed once ($3.00), not twice.
    # terse = $3.00 (resumed) + $1.00 (dated haiku) = $4.00
    # other = $0.00 (synthetic) + $0.60 (cache read)  = $0.60
    assert "Total: $4.60" in output, output

    project_lines = [ln for ln in output.splitlines() if ln.startswith(f"  {TERSE}") or ln.startswith(f"  {OTHER}")]
    assert len(project_lines) == 2, output
    assert f"  {TERSE}  $4.00" in output, output
    assert f"  {OTHER}  $0.60" in output, output

    # The dated model ID and <synthetic> are both priced, so nothing is
    # reported as an unrecognized model.
    assert "unrecognized model name" not in output, output

    # Cache tokens are visible rather than silently folded into the cost.
    assert "2000000 cache-read" in output, output

    # Four distinct sessions survive: the deduped resume counts once.
    assert "(4 session(s))" in output, output
    for session in ("resumed-session", "haiku-session", "synthetic-session", "cache-session"):
        assert session in output, output


def test_end_to_end_without_dedup_would_double_count(tmp_path):
    """Guard the discriminating value: if cross-file dedup regressed, the
    resumed call would be counted twice and the total would be $7.60."""
    _build_tree(tmp_path)

    output = run(tmp_path, days=None, top_n=10)

    assert "Total: $7.60" not in output
    assert f"  {TERSE}  $7.00" not in output
