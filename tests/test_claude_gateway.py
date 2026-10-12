import pytest

from documenteveryday.llm.budget_ledger import BatchBudgetExceeded, BatchBudgetLedger
from documenteveryday.llm.claude_gateway import ClaudeGateway, ClaudeOutputUnusable, ClaudeRefused
from tests.fake_claude import FakeClaudeClient, fake_response, json_response


def make_gateway(respond, limit_dollars=0.50):
    recorded = []
    client = FakeClaudeClient({"": respond})
    gateway = ClaudeGateway(client, "claude-haiku-5-5", 7, BatchBudgetLedger(limit_dollars), recorded.append)
    return gateway, client, recorded


def test_json_request_parses_prices_and_records_the_decision():
    gateway, client, recorded = make_gateway(lambda request: json_response({"tag": "training"}))
    result = gateway.request_json(
        purpose="classify", system="s", prompt="p", schema={"type": "object"}, max_tokens=100, effort="low", clip_id=3
    )
    assert result == {"tag": "training"}
    assert client.requests[0]["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    [decision] = recorded
    assert (decision.batch_id, decision.clip_id, decision.purpose) == (7, 3, "classify")
    assert decision.cost_dollars == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1_000_000)
    assert gateway.ledger.spent_dollars == pytest.approx(decision.cost_dollars)


def test_budget_guard_stops_before_calling_claude():
    gateway, client, recorded = make_gateway(lambda request: fake_response("x"), limit_dollars=0.000001)
    with pytest.raises(BatchBudgetExceeded):
        gateway.request_text(purpose="voice", system="s", prompt="p" * 1000, max_tokens=1000, effort="low")
    assert client.requests == [] and recorded == []


def test_invalid_json_is_still_paid_for_and_logged_then_raised():
    gateway, _, recorded = make_gateway(lambda request: fake_response("not json", stop_reason="max_tokens"))
    with pytest.raises(ClaudeOutputUnusable):
        gateway.request_json(purpose="score", system="s", prompt="p", schema={}, max_tokens=10, effort="low")
    assert recorded[0].decision == {"error": "invalid JSON (max_tokens)"}
    assert gateway.ledger.spent_dollars > 0


def test_refusal_raises_after_counting_its_cost():
    gateway, _, _ = make_gateway(lambda request: fake_response("", stop_reason="refusal"))
    with pytest.raises(ClaudeRefused):
        gateway.request_text(purpose="voice", system="s", prompt="p", max_tokens=10, effort="low")
    assert gateway.ledger.spent_dollars > 0


def test_tool_turn_records_the_tool_calls():
    gateway, _, recorded = make_gateway(lambda request: fake_response(tool_calls=[("retrim_clip", {"a": 1})]))
    gateway.request_turn(purpose="qa", system="s", messages=[], tools=[], max_tokens=10, effort="low")
    assert recorded[0].decision["tool_calls"] == [{"tool": "retrim_clip", "input": {"a": 1}}]
