import json
import re
from datetime import datetime, timezone

from claude_usage.html import build_dashboard_data, render_dashboard
from claude_usage.scanner import UsageRecord


def _rec(day, cwd, sid, model="claude-sonnet-4-6", inp=1_000_000):
    return UsageRecord(datetime.fromisoformat(f"{day}T10:00:00+00:00"), cwd, sid, model, inp, 0, 0, 0)


def test_dashboard_data_fills_quiet_days_and_ranks():
    data = build_dashboard_data([
        _rec("2026-08-10", "/p/a", "s1"),
        _rec("2026-08-12", "/p/b", "s2", inp=2_000_000),
        _rec("2026-08-12", "/p/b", "s3", model="mystery-model"),
    ], top_n=10)
    assert [d["d"] for d in data["daily"]] == ["2026-08-10", "2026-08-11", "2026-08-12"]
    assert data["daily"][1]["cost"] == 0
    assert data["total_cost"] == 9.0
    assert data["projects"][0]["k"] == "/p/b"
    assert data["sessions"][0]["id"] == "s2"
    assert data["unpriced"] == 1
    assert data["mix"]["input"] == 4_000_000


def test_long_project_tail_folds_into_other():
    recs = [_rec("2026-08-10", f"/p/{i}", f"s{i}") for i in range(13)]
    projects = build_dashboard_data(recs, top_n=5)["projects"]
    assert len(projects) == 11 and projects[-1]["k"] == "Other (3 projects)"


def test_rendered_page_embeds_data_and_cannot_break_out_of_script():
    page = render_dashboard([_rec("2026-08-10", "/p/</script><b>", "s1")], top_n=5)
    payload = re.search(r"const DATA = (.*);\n", page).group(1)
    assert "</script>" not in payload
    assert json.loads(payload.replace("<\\/", "</"))["total_cost"] == 3.0


def test_live_flag_only_enabled_when_served():
    recs = [_rec("2026-08-10", "/p/a", "s1")]
    assert "const LIVE = false;" in render_dashboard(recs, top_n=5)
    assert "const LIVE = true;" in render_dashboard(recs, top_n=5, live=True)
