"""Dollar cost of a Claude call from its token usage. Rates are per million tokens, first-party API."""

from dataclasses import dataclass

TOKENS_PER_MILLION = 1_000_000
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class ModelPricing:
    input_dollars_per_million: float
    output_dollars_per_million: float
    long_prompt_input_dollars_per_million: float
    long_prompt_output_dollars_per_million: float
    long_prompt_threshold_tokens: int


MODEL_PRICING = {
    # Haiku 5.5 bills prompts over 100K tokens at a higher rate card.
    "claude-haiku-5-5": ModelPricing(0.10, 0.50, 0.50, 2.50, 100_000),
    "claude-sonnet-5-5": ModelPricing(2.00, 10.00, 2.00, 10.00, 10**12),
    "claude-opus-5-5": ModelPricing(4.00, 20.00, 4.00, 20.00, 10**12),
}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


def pricing_for(model: str) -> ModelPricing:
    if model not in MODEL_PRICING:
        raise ValueError(f"No price list for {model}; add it to MODEL_PRICING before using it.")
    return MODEL_PRICING[model]


def rates_for_prompt(model: str, prompt_tokens: int) -> tuple[float, float]:
    pricing = pricing_for(model)
    if prompt_tokens > pricing.long_prompt_threshold_tokens:
        return pricing.long_prompt_input_dollars_per_million, pricing.long_prompt_output_dollars_per_million
    return pricing.input_dollars_per_million, pricing.output_dollars_per_million


def cost_of_usage(model: str, usage: TokenUsage) -> float:
    input_rate, output_rate = rates_for_prompt(model, usage.prompt_tokens)
    input_cost = input_rate * (
        usage.input_tokens
        + usage.cache_read_input_tokens * CACHE_READ_MULTIPLIER
        + usage.cache_creation_input_tokens * CACHE_WRITE_MULTIPLIER
    )
    return (input_cost + output_rate * usage.output_tokens) / TOKENS_PER_MILLION
