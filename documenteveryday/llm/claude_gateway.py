"""The only door to Claude. Every call is budget-checked first, then priced and logged as an AI decision."""

import json
from collections.abc import Callable
from typing import Any

from documenteveryday.llm.budget_ledger import BatchBudgetLedger
from documenteveryday.llm.pricing import TokenUsage, cost_of_usage
from documenteveryday.storage.repositories import AiDecision

# Real English text averages about four characters per token; three overestimates on purpose, so the
# budget guard errs on the side of stopping early rather than overspending.
CHARACTERS_PER_TOKEN_ESTIMATE = 3


class ClaudeCallFailed(RuntimeError):
    """Any reason a Claude call produced nothing usable: network or API error, refusal, malformed output."""


class ClaudeRefused(ClaudeCallFailed):
    pass


class ClaudeOutputUnusable(ClaudeCallFailed):
    pass


def token_usage_from(response_usage: Any) -> TokenUsage:
    return TokenUsage(
        input_tokens=response_usage.input_tokens,
        output_tokens=response_usage.output_tokens,
        cache_read_input_tokens=getattr(response_usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(response_usage, "cache_creation_input_tokens", 0) or 0,
    )


def response_text(response: Any) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def tool_calls_in(response: Any) -> list[Any]:
    return [block for block in response.content if block.type == "tool_use"]


class ClaudeGateway:
    def __init__(
        self,
        client: Any,
        model: str,
        batch_id: int,
        ledger: BatchBudgetLedger,
        record_decision: Callable[[AiDecision], None],
    ):
        self.client = client
        self.model = model
        self.batch_id = batch_id
        self.ledger = ledger
        self.record_decision = record_decision

    def request_text(
        self, *, purpose: str, system: str, prompt: str, max_tokens: int, effort: str, clip_id: int | None = None
    ) -> str:
        request = self.base_request(system, [{"role": "user", "content": prompt}], max_tokens, effort)
        response, usage = self.create_message(request)
        text = response_text(response)
        self.record(purpose, clip_id, usage, {"text": text[:2000]})
        return text

    def request_json(
        self,
        *,
        purpose: str,
        system: str,
        prompt: str,
        schema: dict,
        max_tokens: int,
        effort: str,
        clip_id: int | None = None,
    ) -> dict:
        request = self.base_request(system, [{"role": "user", "content": prompt}], max_tokens, effort)
        request["output_config"]["format"] = {"type": "json_schema", "schema": schema}
        response, usage = self.create_message(request)
        try:
            parsed = json.loads(response_text(response))
        except json.JSONDecodeError as error:
            self.record(purpose, clip_id, usage, {"error": f"invalid JSON ({response.stop_reason})"})
            raise ClaudeOutputUnusable(f"{purpose}: response was not valid JSON ({response.stop_reason})") from error
        self.record(purpose, clip_id, usage, parsed)
        return parsed

    def request_turn(
        self,
        *,
        purpose: str,
        system: str,
        messages: list,
        tools: list[dict],
        max_tokens: int,
        effort: str,
        clip_id: int | None = None,
    ) -> Any:
        """One turn of a tool-using loop; the caller runs the tools and continues the conversation."""
        request = {**self.base_request(system, messages, max_tokens, effort), "tools": tools}
        response, usage = self.create_message(request)
        tool_calls = [{"tool": call.name, "input": call.input} for call in tool_calls_in(response)]
        self.record(purpose, clip_id, usage, {"tool_calls": tool_calls, "text": response_text(response)[:1000]})
        return response

    def base_request(self, system: str, messages: list, max_tokens: int, effort: str) -> dict:
        return {
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "output_config": {"effort": effort},
        }

    def worst_case_cost(self, request: dict) -> float:
        estimated_prompt_tokens = len(json.dumps(request, default=str)) // CHARACTERS_PER_TOKEN_ESTIMATE
        return cost_of_usage(self.model, TokenUsage(estimated_prompt_tokens, request["max_tokens"]))

    def create_message(self, request: dict) -> tuple[Any, TokenUsage]:
        self.ledger.ensure_affordable(self.worst_case_cost(request))
        try:
            response = self.client.messages.create(model=self.model, **request)
        except Exception as error:  # the SDK already retried; callers only need to know it failed
            raise ClaudeCallFailed(f"{type(error).__name__}: {error}") from error
        usage = token_usage_from(response.usage)
        self.ledger.record(cost_of_usage(self.model, usage))
        if response.stop_reason == "refusal":
            raise ClaudeRefused(f"Claude declined: {getattr(response, 'stop_details', None)}")
        return response, usage

    def record(self, purpose: str, clip_id: int | None, usage: TokenUsage, decision: dict) -> None:
        self.record_decision(
            AiDecision(
                batch_id=self.batch_id,
                clip_id=clip_id,
                purpose=purpose,
                model=self.model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.output_tokens,
                cost_dollars=cost_of_usage(self.model, usage),
                decision=decision,
            )
        )
