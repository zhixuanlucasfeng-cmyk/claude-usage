from pathlib import Path
from datetime import date, datetime, timedelta, timezone

from claude_usage.scanner import UsageRecord
from claude_usage.sources import CodexLimit, CodexScan, TokenEvent, _CodexFile, _read_codex_tail
from claude_usage.widget import build_widget_data

TODAY = date(2026, 10, 9)


def _local_noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12).astimezone().astimezone(timezone.utc)


def test_widget_buckets_today_and_week_per_tool():
    claude = [UsageRecord(_local_noon(TODAY), "/p", "s", "claude-sonnet-4-6", 1_000_000, 0, 0, 0),
              UsageRecord(_local_noon(TODAY), "/h/.power", "s", "claude-sonnet-4-6", 1_000_000, 0, 0, 0),
              UsageRecord(_local_noon(TODAY), "/h/.powerx", "s", "claude-sonnet-4-6", 7, 0, 0, 0)]
    codex = CodexScan(
        [TokenEvent(_local_noon(TODAY), "codex", "gpt", 500),
         TokenEvent(_local_noon(TODAY - timedelta(days=7)), "codex", "gpt", 9)],  # outside the week
        CodexLimit(22.0, datetime(2026, 10, 14, tzinfo=timezone.utc)),
    )
    hermes = [TokenEvent(_local_noon(TODAY - timedelta(days=1)), "deepseek", "deepseek-v4-pro", 70)]
    data = build_widget_data(claude, codex, hermes, TODAY, Path("/h/.power"))
    assert data["power"] == {"tokens": 1_000_000, "cost": 3.0}
    codex.events += [TokenEvent(_local_noon(TODAY), "codex", "gpt", 40, "cx1"),
                     TokenEvent(_local_noon(TODAY), "codex", "gpt", 2, "x", "/h/.power/tasks/1")]
    oc = [TokenEvent(_local_noon(TODAY), "opencode", "m", 300, "oc1")]
    data = build_widget_data(claude, codex, hermes, TODAY, Path("/h/.power"), {"cx1", "oc1"}, oc)
    assert data["today"] == {"claude": 2_000_007, "codex": 542, "deepseek": 0, "claude_cost": 6.0}
    assert data["power"] == {"tokens": 1_000_342, "cost": 3.0}
    assert data["week"][-1]["power"] == 1_000_342 and data["week"][-2]["power"] == 0
    assert data["power_daily"] == [{"d": "2026-10-09", "tokens": 1_000_342, "cost": 3.0,
                                    "claude": 1_000_000, "codex": 42, "deepseek": 0, "opencode": 300}]
    assert [w["d"] for w in data["week"]][-1] == "2026-10-09" and len(data["week"]) == 7
    assert data["week"][-2]["deepseek"] == 70
    assert sum(w["codex"] for w in data["week"]) == 542
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


def test_history_keeps_days_after_logs_are_cleaned(tmp_path):
    from claude_usage.widget import daily_totals, save_history
    f = tmp_path / "daily-history.csv"
    old_day = TODAY - timedelta(days=40)
    claude = [UsageRecord(_local_noon(old_day), "/p", "s", "claude-sonnet-4-6", 1_000_000, 0, 0, 0),
              UsageRecord(_local_noon(TODAY), "/p", "s", "claude-sonnet-4-6", 100, 0, 0, 0)]
    save_history(f, daily_totals(claude, [TokenEvent(_local_noon(TODAY), "codex", "gpt", 5)]))
    # Claude Code deleted the old transcript and part of today's: nothing saved may shrink.
    save_history(f, daily_totals([], [TokenEvent(_local_noon(TODAY), "codex", "gpt", 7)]))
    assert f.read_text().splitlines() == [
        "date,claude,codex,deepseek,claude_cost",
        f"{old_day},1000000,0,0,3.00",
        f"{TODAY},100,7,0,0.00",
    ]


def test_limit_projection_converts_log_spend_into_percent():
    from claude_usage.widget import add_projections
    now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    rec = lambda h, usd: UsageRecord(now - timedelta(hours=h), "/p", "s", "claude-sonnet-4-6", int(usd / 3 * 1e6), 0, 0, 0)
    # Window opened 3h ago. $2.5 spent by the snapshot 30 min ago, $0.5 since; $1 in the last hour.
    claude = [rec(3, 2.0), rec(0.75, 0.5), rec(0.25, 0.5), rec(6, 99.0)]  # the $99 is before the window
    def lim(used):
        return {"five_hour": {"used_percent": used, "resets_at": (now + timedelta(hours=2)).isoformat()},
                "saved_at": (now - timedelta(minutes=30)).isoformat()}
    # 25% for $2.5 -> 10% per dollar
    assert add_projections(lim(25.0), claude, now)["five_hour"]["projection"] == \
        {"now": 30.0, "per_hour": 10.0, "at_reset": 50.0, "full_at": None}
    # 80% for $2.5 -> 32% per dollar: 96% now, 32%/h, 100% in 7.5 min
    p = add_projections(lim(80.0), claude, now)["five_hour"]["projection"]
    assert p["now"] == 96.0 and abs(datetime.fromisoformat(p["full_at"]) - (now + timedelta(minutes=7.5))) < timedelta(seconds=1)
    assert add_projections(lim(0.0), claude, now)["five_hour"]["projection"] is None
