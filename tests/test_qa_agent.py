from pathlib import Path

import pytest

from documenteveryday.domain import CaptionCue, ClipPlan, ClipProblem
from documenteveryday.llm.budget_ledger import BatchBudgetLedger
from documenteveryday.llm.claude_gateway import ClaudeGateway
from documenteveryday.qa.clip_checks import ClipUnderReview, find_unfinished_sentence
from documenteveryday.qa.clip_workbench import ClipWorkbench
from documenteveryday.qa.qa_agent import ClipQaAgent
from tests.conftest import evenly_spoken_words
from tests.fake_claude import FakeClaudeClient, fake_response

WORDS = evenly_spoken_words(["one two three four five six seven eight nine ten"] * 6)


class ScriptedClaude(FakeClaudeClient):
    def __init__(self, responses):
        super().__init__({"": lambda request: responses.pop(0)})


def make_agent(responses, find_problems=find_unfinished_sentence):
    recorded = []
    client = ScriptedClaude(list(responses))
    gateway = ClaudeGateway(client, "claude-haiku-5-5", 1, BatchBudgetLedger(0.5), recorded.append)
    return ClipQaAgent(gateway, find_problems=find_problems), client, recorded


def make_workbench(last_index=38):
    renders = []

    def render(plan, cues):
        renders.append(plan)
        return Path(f"render_{len(renders)}.mp4")

    plan = ClipPlan(1, 0, last_index, 0.0, WORDS[last_index].end_seconds)
    clip = ClipUnderReview(plan, WORDS, (CaptionCue(0, 1, "one two"),), Path("render_0.mp4"))
    return ClipWorkbench(clip, render, lambda plan: [CaptionCue(0, 1, "rebuilt")]), renders


def test_clean_clip_passes_without_calling_claude():
    agent, client, _ = make_agent([])
    outcome = agent.review(make_workbench(last_index=39)[0], clip_id=1)
    assert outcome.status == "passed" and client.requests == []


def test_agent_retrims_rerenders_and_reports_the_fix():
    agent, client, recorded = make_agent(
        [fake_response(tool_calls=[("retrim_clip", {"first_word_index": 0, "last_word_index": 39,
                                                     "reason": "end on the full sentence"})])]
    )  # fmt: skip
    workbench, renders = make_workbench()
    outcome = agent.review(workbench, clip_id=5)
    assert outcome.status == "fixed"
    assert outcome.fixes == ("retrim_clip: end on the full sentence",)
    assert workbench.current.plan.last_word_index == 39 and len(renders) == 1
    assert workbench.current.cues[0].text == "rebuilt"
    assert recorded[0].clip_id == 5 and recorded[0].purpose == "qa_agent"
    assert "ENDS_MID_SENTENCE" in client.requests[0]["messages"][0]["content"]


def test_agent_flags_after_two_fixes_that_do_not_help():
    bad_retrim = fake_response(
        tool_calls=[("retrim_clip", {"first_word_index": 0, "last_word_index": 37, "reason": "try"})]
    )
    agent, client, _ = make_agent([bad_retrim, bad_retrim])
    outcome = agent.review(make_workbench()[0], clip_id=1)
    assert outcome.status == "flagged" and "Still failing after 2" in outcome.summary
    assert len(client.requests) == 2
    second_turn = client.requests[1]["messages"]
    assert second_turn[-1]["content"][0]["type"] == "tool_result"


def test_agent_can_hand_the_clip_to_me_with_a_reason():
    agent, _, _ = make_agent([fake_response(tool_calls=[("flag_for_review", {"reason": "black frames"})])])
    outcome = agent.review(make_workbench()[0], clip_id=1)
    assert (outcome.status, outcome.summary) == ("flagged", "black frames")


def test_invalid_tool_input_is_reported_back_not_crashed_on():
    agent, client, _ = make_agent(
        [
            fake_response(tool_calls=[("retrim_clip", {"first_word_index": 50, "last_word_index": 10, "reason": "x"})]),
            fake_response(tool_calls=[("flag_for_review", {"reason": "gave up"})]),
        ]
    )
    outcome = agent.review(make_workbench()[0], clip_id=1)
    assert outcome.status == "flagged" and outcome.fixes == ()
    rejected_result = client.requests[1]["messages"][-1]["content"][0]
    assert rejected_result["is_error"] and "Rejected" in rejected_result["content"]


def test_rewrite_caption_changes_english_line_for_arabic():
    workbench, _ = make_workbench()
    workbench.current = ClipUnderReview(
        workbench.current.plan, WORDS, (CaptionCue(0, 1, "ازيك", is_arabic=True),), Path("x.mp4")
    )
    workbench.rewrite_caption(0, "How are you")
    assert workbench.current.cues[0].text == "ازيك"
    assert workbench.current.cues[0].english_translation == "How are you"


@pytest.mark.ffmpeg
def test_real_render_retrim_fixes_a_clip_ending_mid_sentence(synthetic_landscape_video, tmp_path):
    from documenteveryday.production.clip_production import ClipProductionRequest, produce_clip
    from documenteveryday.qa.clip_checks import find_clip_problems

    def render(plan, cues):
        return produce_clip(
            ClipProductionRequest(synthetic_landscape_video, plan.start_seconds, plan.end_seconds, cues, "Hook",
                                  tmp_path, "clip_1")
        )  # fmt: skip

    plan = ClipPlan(1, 0, 38, 0.0, WORDS[38].end_seconds + 0.05)
    clip = ClipUnderReview(plan, WORDS, (), render(plan, []))
    workbench = ClipWorkbench(clip, render, lambda plan: [])
    agent, _, _ = make_agent(
        [fake_response(tool_calls=[("retrim_clip", {"first_word_index": 0, "last_word_index": 39, "reason": "r"})])],
        find_problems=find_clip_problems,
    )
    outcome = agent.review(workbench, clip_id=1)
    assert outcome.status == "fixed", outcome.summary
    assert find_clip_problems(workbench.current) == []


def test_problem_descriptions_reach_the_model():
    agent, client, _ = make_agent(
        [fake_response(tool_calls=[("flag_for_review", {"reason": "r"})])],
        find_problems=lambda clip: [ClipProblem("BAD_FRAMING", "Black frames from 1.0s to 3.0s")],
    )
    agent.review(make_workbench()[0], clip_id=1)
    assert "Black frames from 1.0s" in client.requests[0]["messages"][0]["content"]
