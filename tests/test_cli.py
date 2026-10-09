import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_usage.cli import build_report, run
from claude_usage.scanner import UsageRecord


def _write_record(path: Path, timestamp: str, cwd: str, session_id: str, model: str, input_tokens: int, output_tokens: int) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": timestamp,
            "cwd": cwd,
            "sessionId": session_id,
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        }) + "\n")


def test_run_produces_report_with_project_and_session_breakdown(tmp_path):
    project_dir = tmp_path / "-Users-alice-terse"
    project_dir.mkdir()
    jsonl_path = project_dir / "session1.jsonl"
    _write_record(jsonl_path, "2026-08-12T10:00:00.000Z", "/Users/alice/terse", "session1", "claude-sonnet-4-6", 1_000_000, 0)

    output = run(tmp_path, days=None, top_n=10)

    assert "/Users/alice/terse" in output
    assert "session1" in output
    assert "$3.00" in output
    assert "Total: $3.00" in output


def test_run_raises_when_projects_dir_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    try:
        run(missing, days=None, top_n=10)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_run_filters_by_days(tmp_path):
    project_dir = tmp_path / "-Users-alice-terse"
    project_dir.mkdir()
    jsonl_path = project_dir / "session1.jsonl"

    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat().replace("+00:00", "Z")
    recent_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_record(jsonl_path, old_timestamp, "/Users/alice/terse", "old-session", "claude-sonnet-4-6", 1_000_000, 0)
    _write_record(jsonl_path, recent_timestamp, "/Users/alice/terse", "recent-session", "claude-sonnet-4-6", 1_000_000, 0)

    output = run(tmp_path, days=7, top_n=10)

    assert "recent-session" in output
    assert "old-session" not in output


def test_build_report_notes_unpriced_records():
    records = [
        UsageRecord(
            timestamp=datetime.fromisoformat("2026-08-12T00:00:00"),
            cwd="/proj",
            session_id="s1",
            model="some-future-model",
            input_tokens=100,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
    ]

    output = build_report(records, top_n=10)

    assert "unrecognized model name" in output


def test_build_report_shows_cache_tokens():
    """Cache-read tokens dominate real usage; hiding them makes the dollar
    figures look inconsistent with the token counts shown beside them."""
    records = [
        UsageRecord(
            timestamp=datetime.fromisoformat("2026-08-12T00:00:00"),
            cwd="/proj",
            session_id="s1",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=12_345,
            cache_read_input_tokens=6_789_000,
        )
    ]

    output = build_report(records, top_n=10)

    assert "6789000" in output
    assert "12345" in output


def test_build_report_does_not_flag_synthetic_as_unrecognized():
    records = [
        UsageRecord(
            timestamp=datetime.fromisoformat("2026-08-12T00:00:00"),
            cwd="/proj",
            session_id="s1",
            model="<synthetic>",
            input_tokens=1000,
            output_tokens=1000,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
    ]

    output = build_report(records, top_n=10)

    assert "unrecognized model name" not in output
    assert "Total: $0.00" in output
