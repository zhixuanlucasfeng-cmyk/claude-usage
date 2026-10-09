import re

# Price snapshot as of 2026-10-09 (USD per 1M tokens). Anthropic pricing
# changes over time; this table is not fetched live and needs manual updates.
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
}

# Claude Code sometimes logs a short alias instead of the full model ID
# (e.g. for subagent dispatch). Map those to a full ID before pricing lookup.
_ALIASES: dict[str, str] = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-4-5",
}

# Models that are real and known but never billed. "<synthetic>" is the
# placeholder Claude Code logs for locally generated (non-API) messages, so it
# costs $0 — it is not an unrecognized model we failed to price.
_KNOWN_ZERO_COST_MODELS = {"<synthetic>"}

# Real logs frequently carry a dated model ID (claude-haiku-4-5-20251001).
# The date suffix is a snapshot marker, not a distinct price tier.
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")

# Newer models publish a cache-read price that is not input x 0.1.
_CACHE_READ_PRICE: dict[str, float] = {
    "claude-fable-5-1": 0.25,
    "claude-opus-5-5": 0.20,
    "claude-sonnet-5-5": 0.20,
}

_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.1


def resolve_model(model: str) -> str:
    resolved = _ALIASES.get(model, model)
    return _DATE_SUFFIX_RE.sub("", resolved)


def cost_for_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
) -> float | None:
    resolved = resolve_model(model)
    if resolved in _KNOWN_ZERO_COST_MODELS:
        # A real, known cost of zero — distinct from None ("cannot price this").
        return 0.0
    prices = PRICING.get(resolved)
    if prices is None:
        return None
    input_price, output_price = prices
    cache_read_price = _CACHE_READ_PRICE.get(resolved, input_price * _CACHE_READ_MULTIPLIER)
    return (
        input_tokens * input_price
        + output_tokens * output_price
        + cache_creation_input_tokens * input_price * _CACHE_WRITE_MULTIPLIER
        + cache_read_input_tokens * cache_read_price
    ) / 1_000_000
