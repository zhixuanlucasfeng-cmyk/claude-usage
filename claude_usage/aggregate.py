from dataclasses import dataclass
from typing import Callable

from claude_usage.pricing import cost_for_tokens
from claude_usage.scanner import UsageRecord


@dataclass
class AggregateResult:
    key: str
    total_cost: float
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    unpriced_count: int


def _cost_and_flag(record: UsageRecord) -> tuple[float, bool]:
    cost = cost_for_tokens(
        record.model,
        record.input_tokens,
        record.output_tokens,
        record.cache_creation_input_tokens,
        record.cache_read_input_tokens,
    )
    if cost is None:
        return 0.0, True
    return cost, False


def _aggregate_by(records: list[UsageRecord], key_fn: Callable[[UsageRecord], str]) -> dict[str, AggregateResult]:
    results: dict[str, AggregateResult] = {}
    for record in records:
        key = key_fn(record)
        cost, unpriced = _cost_and_flag(record)
        if key not in results:
            results[key] = AggregateResult(
                key=key,
                total_cost=0.0,
                input_tokens=0,
                output_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                unpriced_count=0,
            )
        agg = results[key]
        agg.total_cost += cost
        agg.input_tokens += record.input_tokens
        agg.output_tokens += record.output_tokens
        agg.cache_creation_input_tokens += record.cache_creation_input_tokens
        agg.cache_read_input_tokens += record.cache_read_input_tokens
        agg.unpriced_count += 1 if unpriced else 0
    return results


def aggregate_by_project(records: list[UsageRecord]) -> list[AggregateResult]:
    grouped = _aggregate_by(records, lambda r: r.cwd)
    return sorted(grouped.values(), key=lambda a: a.total_cost, reverse=True)


def aggregate_by_date(records: list[UsageRecord]) -> list[AggregateResult]:
    grouped = _aggregate_by(records, lambda r: r.timestamp.date().isoformat())
    return sorted(grouped.values(), key=lambda a: a.key, reverse=True)


def aggregate_by_session(records: list[UsageRecord], top_n: int) -> list[AggregateResult]:
    grouped = _aggregate_by(records, lambda r: r.session_id)
    ranked = sorted(grouped.values(), key=lambda a: a.total_cost, reverse=True)
    return ranked[:top_n]


def total_unpriced_count(records: list[UsageRecord]) -> int:
    return sum(1 for r in records if _cost_and_flag(r)[1])
