import pytest

from documenteveryday.llm.budget_ledger import BatchBudgetExceeded, BatchBudgetLedger
from documenteveryday.llm.pricing import TokenUsage, cost_of_usage


def test_haiku_cost_uses_per_million_rates():
    assert cost_of_usage("claude-haiku-5-5", TokenUsage(100_000, 100_000)) == pytest.approx(0.06)


def test_haiku_long_prompts_use_the_higher_rate_card():
    assert cost_of_usage("claude-haiku-5-5", TokenUsage(200_000, 0)) == pytest.approx(0.10)


def test_cache_reads_are_discounted():
    usage = TokenUsage(0, 0, cache_read_input_tokens=100_000)
    assert cost_of_usage("claude-haiku-5-5", usage) == pytest.approx(0.001)


def test_unknown_model_is_refused_rather_than_priced_at_zero():
    with pytest.raises(ValueError):
        cost_of_usage("claude-mystery", TokenUsage(1, 1))


def test_ledger_blocks_a_call_that_could_cross_the_limit():
    ledger = BatchBudgetLedger(0.50, already_spent_dollars=0.45)
    ledger.ensure_affordable(0.05)
    with pytest.raises(BatchBudgetExceeded):
        ledger.ensure_affordable(0.06)
