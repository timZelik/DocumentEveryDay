"""A stand-in for anthropic.Anthropic that answers by matching the system prompt. Never spends money."""

import json
from collections.abc import Callable
from types import SimpleNamespace


def fake_response(text: str = "", tool_calls=(), stop_reason: str = "end_turn", input_tokens=1000, output_tokens=200):
    content = [SimpleNamespace(type="text", text=text)] if text else []
    content += [
        SimpleNamespace(type="tool_use", id=f"toolu_{index}", name=name, input=tool_input)
        for index, (name, tool_input) in enumerate(tool_calls)
    ]
    usage = SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )
    return SimpleNamespace(content=content, usage=usage, stop_reason=stop_reason, stop_details=None)


def json_response(payload: dict, **usage) -> SimpleNamespace:
    return fake_response(text=json.dumps(payload), **usage)


class FakeClaudeClient:
    def __init__(self, routes: dict[str, Callable[[dict], SimpleNamespace]]):
        self.routes = routes
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **request) -> SimpleNamespace:
        self.requests.append(request)
        for system_prompt_fragment, respond in self.routes.items():
            if system_prompt_fragment in request["system"]:
                return respond(request)
        raise AssertionError(f"No fake route for system prompt: {request['system'][:80]}")
