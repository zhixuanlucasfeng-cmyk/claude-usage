from datetime import datetime

from claude_usage.aggregate import (
    aggregate_by_date,
    aggregate_by_project,
    aggregate_by_session,
    total_unpriced_count,
)
from claude_usage.scanner import UsageRecord


def _record(
    cwd,
    session_id,
    date_str,
    model="claude-sonnet-4-6",
    input_tokens=1_000_000,
    output_tokens=0,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
):
    return UsageRecord(
        timestamp=datetime.fromisoformat(date_str),
        cwd=cwd,
        session_id=session_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )


def test_aggregate_by_project_sums_and_sorts_descending():
    records = [
        _record("/proj/a", "s1", "2026-08-10T00:00:00", input_tokens=1_000_000),
        _record("/proj/b", "s2", "2026-08-11T00:00:00", input_tokens=500_000),
        _record("/proj/c", "s3", "2026-08-10T00:00:00", input_tokens=2_000_000),
    ]

    result = aggregate_by_project(records)

    # Verify descending cost order with genuinely different costs
    assert [r.key for r in result] == ["/proj/c", "/proj/a", "/proj/b"]
    assert result[0].total_cost == 6.0  # 2M tokens * $3/1M
    assert result[1].total_cost == 3.0  # 1M tokens * $3/1M
    assert result[2].total_cost == 1.5  # 0.5M tokens * $3/1M


def test_aggregate_by_project_with_tied_costs():
    records = [
        _record("/proj/a", "s1", "2026-08-10T00:00:00"),
        _record("/proj/a", "s2", "2026-08-11T00:00:00"),
        _record("/proj/b", "s3", "2026-08-10T00:00:00", input_tokens=2_000_000),
    ]

    result = aggregate_by_project(records)

    # When costs are tied, order is not defined; just verify both are present with correct costs
    by_key = {r.key: r.total_cost for r in result}
    assert by_key == {"/proj/a": 6.0, "/proj/b": 6.0}


def test_aggregate_by_date_sums_by_day_and_sorts_newest_first():
    records = [
        _record("/proj/a", "s1", "2026-08-10T09:00:00"),
        _record("/proj/a", "s2", "2026-08-10T14:00:00"),
        _record("/proj/a", "s3", "2026-08-11T09:00:00"),
    ]

    result = aggregate_by_date(records)

    assert [r.key for r in result] == ["2026-08-11", "2026-08-10"]
    assert result[1].total_cost == 6.0  # two 1M-token records on 2026-08-10


def test_aggregate_by_session_returns_top_n_by_cost():
    records = [
        _record("/proj/a", "cheap", "2026-08-10T00:00:00", input_tokens=100_000),
        _record("/proj/a", "expensive", "2026-08-10T00:00:00", input_tokens=5_000_000),
        _record("/proj/a", "medium", "2026-08-10T00:00:00", input_tokens=1_000_000),
    ]

    result = aggregate_by_session(records, top_n=2)

    assert [r.key for r in result] == ["expensive", "medium"]


def test_total_unpriced_count_counts_unknown_models():
    records = [
        _record("/proj/a", "s1", "2026-08-10T00:00:00", model="claude-sonnet-4-6"),
        _record("/proj/a", "s2", "2026-08-10T00:00:00", model="some-future-model"),
    ]

    assert total_unpriced_count(records) == 1


def test_total_unpriced_count_excludes_synthetic_and_dated_models():
    records = [
        _record("/proj/a", "s1", "2026-08-10T00:00:00", model="<synthetic>"),
        _record("/proj/a", "s2", "2026-08-10T00:00:00", model="claude-haiku-4-5-20251001"),
    ]

    assert total_unpriced_count(records) == 0


def test_aggregate_sums_cache_tokens():
    records = [
        _record(
            "/proj/a", "s1", "2026-08-10T00:00:00",
            input_tokens=100, cache_creation_input_tokens=1_000, cache_read_input_tokens=3_200_000,
        ),
        _record(
            "/proj/a", "s2", "2026-08-10T00:00:00",
            input_tokens=100, cache_creation_input_tokens=500, cache_read_input_tokens=800_000,
        ),
    ]

    result = aggregate_by_project(records)

    assert len(result) == 1
    assert result[0].cache_creation_input_tokens == 1_500
    assert result[0].cache_read_input_tokens == 4_000_000


def test_aggregate_by_session_and_date_also_carry_cache_tokens():
    records = [
        _record(
            "/proj/a", "s1", "2026-08-10T00:00:00",
            cache_creation_input_tokens=7, cache_read_input_tokens=11,
        ),
    ]

    assert aggregate_by_session(records, top_n=1)[0].cache_read_input_tokens == 11
    assert aggregate_by_date(records)[0].cache_creation_input_tokens == 7
