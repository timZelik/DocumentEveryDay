"""The agentic QA step: when checks fail, Claude picks a tool to fix the clip, the checks re-run, and after
two fixes that still fail the clip is flagged for my review with the reason."""

from collections.abc import Callable
from typing import Any

from documenteveryday.domain import ClipProblem, QaOutcome
from documenteveryday.llm.claude_gateway import ClaudeGateway, response_text, tool_calls_in
from documenteveryday.llm.prompt_formatting import format_timestamp
from documenteveryday.qa.clip_checks import ClipUnderReview, find_clip_problems
from documenteveryday.qa.clip_workbench import ClipWorkbench, InvalidToolInput

MAXIMUM_FIX_ATTEMPTS = 2
CONTEXT_WORDS_AROUND_CLIP = 40

QA_SYSTEM_PROMPT = """You are the QA step of a pipeline that cuts vertical 15-60 second clips from someone's \
filmed evening. Automated checks found problems with one clip. Fix them with your tools; the checks re-run \
automatically after every fix, and you get at most two fixes.

- retrim_clip: move the cut to a new first and last word index, using the indexed words shown. Use it for a \
cut mid-word or mid-sentence, silence at either edge, or a clip outside 15-60 seconds. Keep the moment that \
was picked; end on a word that finishes a sentence.
- rewrite_caption: replace one caption's text. Use it for a caption too long to fit (at most 24 characters \
per line, 2 lines), or a missing English translation of Arabic. Keep the speaker's meaning.
- flag_for_review: hand the clip to the human with a one-sentence reason. Use it when the problem can't be \
fixed with these tools, such as black frames, framing, or long silence in the middle of the clip.

Call exactly one tool per turn and give a short reason the human will read."""

QA_TOOLS = [
    {
        "name": "retrim_clip",
        "description": "Re-cut the clip so it starts at first_word_index and ends at last_word_index (inclusive).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "first_word_index": {"type": "integer"},
                "last_word_index": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["first_word_index", "last_word_index", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rewrite_caption",
        "description": "Replace caption cue_index's text. For an Arabic caption this replaces its English line.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "cue_index": {"type": "integer"},
                "new_text": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["cue_index", "new_text", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_for_review",
        "description": "Stop and hand this clip to the human, saying what is wrong.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]


def describe_problems(problems: list[ClipProblem]) -> str:
    return "\n".join(f"- {problem.code}: {problem.detail}" for problem in problems)


def describe_words_around_clip(clip: ClipUnderReview) -> str:
    first_shown = max(0, clip.plan.first_word_index - CONTEXT_WORDS_AROUND_CLIP)
    last_shown = min(len(clip.transcript_words) - 1, clip.plan.last_word_index + CONTEXT_WORDS_AROUND_CLIP)
    lines = []
    for index in range(first_shown, last_shown + 1):
        word = clip.transcript_words[index]
        inside_marker = "*" if clip.plan.first_word_index <= index <= clip.plan.last_word_index else " "
        lines.append(f"{inside_marker}{index} {word.start_seconds:.2f}-{word.end_seconds:.2f} {word.text}")
    return "\n".join(lines)


def describe_captions(clip: ClipUnderReview) -> str:
    return "\n".join(
        f"[{index}] {cue.start_seconds:.1f}-{cue.end_seconds:.1f}s {cue.text}"
        + (f" | English: {cue.english_translation or '(missing)'}" if cue.is_arabic else "")
        for index, cue in enumerate(clip.cues)
    )


def describe_clip_for_review(clip: ClipUnderReview, problems: list[ClipProblem]) -> str:
    plan = clip.plan
    return (
        f"Clip: words {plan.first_word_index}-{plan.last_word_index}, {format_timestamp(plan.start_seconds)} to "
        f"{format_timestamp(plan.end_seconds)} ({plan.duration_seconds:.1f}s). Picked because: {plan.pick_reason}\n\n"
        f"Problems:\n{describe_problems(problems)}\n\n"
        f"Words (index start-end text; * = inside the clip):\n{describe_words_around_clip(clip)}\n\n"
        f"Captions:\n{describe_captions(clip)}"
    )


def tool_result(tool_call: Any, content: str, is_error: bool = False) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_call.id, "content": content, "is_error": is_error}


class ClipQaAgent:
    def __init__(
        self,
        gateway: ClaudeGateway,
        find_problems: Callable[[ClipUnderReview], list[ClipProblem]] = find_clip_problems,
        maximum_fix_attempts: int = MAXIMUM_FIX_ATTEMPTS,
    ):
        self.gateway = gateway
        self.find_problems = find_problems
        self.maximum_fix_attempts = maximum_fix_attempts

    def review(self, workbench: ClipWorkbench, clip_id: int) -> QaOutcome:
        problems = self.find_problems(workbench.current)
        if not problems:
            return QaOutcome("passed", "All automated checks passed, so no AI call was needed.")
        messages: list[dict] = [{"role": "user", "content": describe_clip_for_review(workbench.current, problems)}]
        return self.fix_until_clean(workbench, clip_id, messages)

    def fix_until_clean(self, workbench: ClipWorkbench, clip_id: int, messages: list[dict]) -> QaOutcome:
        fixes: list[str] = []
        for attempt in range(1, self.maximum_fix_attempts + 1):
            response = self.gateway.request_turn(
                purpose="qa_agent", system=QA_SYSTEM_PROMPT, messages=messages, tools=QA_TOOLS,
                max_tokens=8000, effort="medium", clip_id=clip_id,
            )  # fmt: skip
            messages.append({"role": "assistant", "content": response.content})
            tool_calls = tool_calls_in(response)
            if not tool_calls:
                return QaOutcome("flagged", f"QA agent gave no fix: {response_text(response)[:300]}", tuple(fixes))
            chosen_call, ignored_calls = tool_calls[0], tool_calls[1:]
            if chosen_call.name == "flag_for_review":
                return QaOutcome("flagged", chosen_call.input["reason"], tuple(fixes))
            result_text, is_error = self.apply_tool(workbench, chosen_call)
            if not is_error:
                fixes.append(f"{chosen_call.name}: {chosen_call.input['reason']}")
            problems = self.find_problems(workbench.current)
            if not problems:
                return QaOutcome("fixed", "Fixed by the QA agent; all checks pass now.", tuple(fixes))
            if attempt == self.maximum_fix_attempts:
                summary = f"Still failing after {attempt} fix attempts: {describe_problems(problems)}"
                return QaOutcome("flagged", summary, tuple(fixes))
            messages.append(
                {
                    "role": "user",
                    "content": [
                        tool_result(chosen_call, f"{result_text}\nRemaining problems:\n{describe_problems(problems)}",
                                    is_error),
                        *(tool_result(call, "Ignored: one tool per turn.", True) for call in ignored_calls),
                    ],
                }
            )  # fmt: skip
        raise AssertionError("unreachable: the loop always returns on its last attempt")

    def apply_tool(self, workbench: ClipWorkbench, tool_call: Any) -> tuple[str, bool]:
        try:
            if tool_call.name == "retrim_clip":
                arguments = tool_call.input
                return workbench.retrim_clip(arguments["first_word_index"], arguments["last_word_index"]), False
            if tool_call.name == "rewrite_caption":
                return workbench.rewrite_caption(tool_call.input["cue_index"], tool_call.input["new_text"]), False
        except InvalidToolInput as error:
            return f"Rejected: {error}", True
        return f"Unknown tool {tool_call.name}.", True
