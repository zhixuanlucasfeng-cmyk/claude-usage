from claude_usage.pricing import resolve_model, cost_for_tokens


def test_resolve_model_alias():
    assert resolve_model("opus") == "claude-opus-5-5"
    assert resolve_model("sonnet") == "claude-sonnet-5-5"
    assert resolve_model("haiku") == "claude-haiku-4-5"


def test_resolve_model_passthrough_for_full_id():
    assert resolve_model("claude-opus-4-8") == "claude-opus-4-8"


def test_cost_for_tokens_known_model():
    cost = cost_for_tokens(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost == 3.0


def test_cost_for_tokens_includes_output_tokens():
    cost = cost_for_tokens(
        "claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=1_000_000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost == 15.0


def test_cost_for_tokens_includes_cache_write_and_read():
    cost = cost_for_tokens(
        "claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    # 1M cache-write tokens at $3 * 1.25 = $3.75; 1M cache-read tokens at $3 * 0.1 = $0.30
    assert cost == 3.75 + 0.3


def test_cost_for_tokens_resolves_alias():
    cost = cost_for_tokens(
        "opus",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost == 4.0


def test_cost_for_tokens_uses_published_cache_read_price():
    # Opus 5.5 cache reads are $0.20/1M, not input x 0.1 ($0.40)
    cost = cost_for_tokens(
        "claude-opus-5-5",
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=1_000_000,
    )
    assert cost == 0.2


def test_cost_for_tokens_unknown_model_returns_none():
    cost = cost_for_tokens(
        "some-future-model",
        input_tokens=1000,
        output_tokens=1000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost is None


def test_resolve_model_strips_date_suffix():
    assert resolve_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert resolve_model("claude-sonnet-5-20260101") == "claude-sonnet-5"


def test_resolve_model_leaves_non_date_suffixes_alone():
    # Aliases must not be mangled, and version-looking suffixes that are not
    # an 8-digit date must survive untouched.
    assert resolve_model("opus") == "claude-opus-5-5"
    assert resolve_model("claude-opus-4-8") == "claude-opus-4-8"
    assert resolve_model("claude-haiku-4-5-2025") == "claude-haiku-4-5-2025"
    assert resolve_model("claude-haiku-4-5-202510011") == "claude-haiku-4-5-202510011"


def test_cost_for_tokens_prices_dated_model_id_like_the_bare_one():
    dated = cost_for_tokens(
        "claude-haiku-4-5-20251001",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    bare = cost_for_tokens(
        "claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert dated == 1.0
    assert dated == bare


def test_cost_for_tokens_synthetic_model_is_a_known_zero_not_unpriced():
    cost = cost_for_tokens(
        "<synthetic>",
        input_tokens=1000,
        output_tokens=1000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert cost == 0.0
    assert cost is not None
