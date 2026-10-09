from datetime import date, datetime, timedelta, timezone

from claude_usage.scanner import UsageRecord
from claude_usage.sources import CodexLimit, CodexScan, TokenEvent, _CodexFile, _read_codex_tail
from claude_usage.widget import build_widget_data

TODAY = date(2026, 10, 9)


def _local_noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12).astimezone().astimezone(timezone.utc)


def test_widget_buckets_today_and_week_per_tool():
    claude = [UsageRecord(_local_noon(TODAY), "/p", "s", "claude-sonnet-4-6", 1_000_000, 0, 0, 0)]
    codex = CodexScan(
        [TokenEvent(_local_noon(TODAY), "codex", "gpt", 500),
         TokenEvent(_local_noon(TODAY - timedelta(days=7)), "codex", "gpt", 9)],  # outside the week
        CodexLimit(22.0, datetime(2026, 10, 14, tzinfo=timezone.utc)),
    )
    hermes = [TokenEvent(_local_noon(TODAY - timedelta(days=1)), "deepseek", "deepseek-v4-pro", 70)]
    data = build_widget_data(claude, codex, hermes, TODAY)
    assert data["today"] == {"claude": 1_000_000, "codex": 500, "deepseek": 0, "claude_cost": 3.0}
    assert [w["d"] for w in data["week"]][-1] == "2026-10-09" and len(data["week"]) == 7
    assert data["week"][-2]["deepseek"] == 70
    assert sum(w["codex"] for w in data["week"]) == 500
    assert data["codex_limit"]["used_percent"] == 22.0


def _tc(ts, total, last):
    return ('{"timestamp":"%s","type":"event_msg","payload":{"type":"token_count","info":'
            '{"total_token_usage":{"input_tokens":%d,"output_tokens":0},'
            '"last_token_usage":{"input_tokens":%d,"output_tokens":0}}}}\n' % (ts, total, last))


def test_codex_counts_increments_and_reads_only_appended_lines(tmp_path):
    f = tmp_path / "rollout.jsonl"
    f.write_text(_tc("2026-10-09T08:00:00Z", 100, 100) + _tc("2026-10-09T08:00:01Z", 100, 100))
    st = _CodexFile()
    _read_codex_tail(f, st)
    assert [e.tokens for e in st.events] == [100]  # repeated total is not double counted
    with f.open("a") as fh:
        fh.write(_tc("2026-10-09T08:01:00Z", 250, 150) + '{"partial')
    _read_codex_tail(f, st)
    assert [e.tokens for e in st.events] == [100, 150]
    assert st.offset == len(f.read_bytes()) - len('{"partial')  # half line left for later


def test_read_claude_limits_accepts_epoch_and_iso(tmp_path):
    from claude_usage.widget import read_claude_limits
    f = tmp_path / "claude-limits.json"
    assert read_claude_limits(f) is None  # no file yet
    f.write_text('{"rate_limits":{"five_hour":{"used_percentage":23.4,"resets_at":1791958000},'
                 '"seven_day":{"used_percentage":41,"resets_at":"2026-10-14T03:00:00Z"}},"saved_at":1791544381}')
    lim = read_claude_limits(f)
    assert lim["five_hour"]["used_percent"] == 23.4
    assert lim["five_hour"]["resets_at"].startswith("2026-")
    assert lim["seven_day"]["resets_at"] == "2026-10-14T03:00:00+00:00"
    f.write_text('{"rate_limits": null}')
    assert read_claude_limits(f) is None
