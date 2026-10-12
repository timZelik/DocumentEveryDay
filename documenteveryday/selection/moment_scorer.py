"""Scores candidate moments against MY good-clip rule, which is read fresh from an editable text file."""

from collections.abc import Sequence

from documenteveryday.domain import GoodClipCriterion, ScoredMoment, Segment, SegmentClassification
from documenteveryday.llm.claude_gateway import ClaudeGateway
from documenteveryday.llm.prompt_formatting import describe_segments

MAXIMUM_SCORE = 10

SCORER_SYSTEM_PROMPT_TEMPLATE = """You pick the best moments from the transcript of someone's after-work \
filming session, to cut into 15-60 second vertical clips. Apply their rule exactly as written:

<good_clip_rule>
{rule_text}
</good_clip_rule>

A moment is one or more consecutive segments from the same video, together roughly 15-60 seconds. Propose \
up to 15 non-overlapping moments, best first. Score each 0-10 for how well it satisfies the rule (7+ means \
clearly worth posting). List which rule criteria it shows. The reason is one plain sentence the speaker will \
read on a review card, saying what happens and why it fits the rule. Set privacy_concern to a short \
description if the speaker mentions showing personal information on screen, otherwise an empty string. \
You only have the transcript: judge visuals from what is said, and never invent what is on screen."""

MOMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "first_segment_index": {"type": "integer"},
                    "last_segment_index": {"type": "integer"},
                    "score": {"type": "integer"},
                    "criteria": {
                        "type": "array",
                        "items": {"type": "string", "enum": [criterion.value for criterion in GoodClipCriterion]},
                    },
                    "reason": {"type": "string"},
                    "privacy_concern": {"type": "string"},
                },
                "required": [
                    "first_segment_index", "last_segment_index", "score", "criteria", "reason", "privacy_concern",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["moments"],
    "additionalProperties": False,
}  # fmt: skip


def parse_moments(response: dict) -> list[ScoredMoment]:
    return [
        ScoredMoment(
            first_segment_index=item["first_segment_index"],
            last_segment_index=item["last_segment_index"],
            score=max(0, min(MAXIMUM_SCORE, item["score"])),
            criteria=tuple(dict.fromkeys(GoodClipCriterion(criterion) for criterion in item["criteria"])),
            reason=item["reason"],
            privacy_concern=item["privacy_concern"].strip(),
        )
        for item in response["moments"]
    ]


class ClaudeMomentScorer:
    def __init__(self, gateway: ClaudeGateway, rule_text: str):
        self.gateway = gateway
        self.rule_text = rule_text

    def score(
        self, segments: Sequence[Segment], classifications: dict[int, SegmentClassification]
    ) -> list[ScoredMoment]:
        if not segments:
            return []
        response = self.gateway.request_json(
            purpose="score_moments",
            system=SCORER_SYSTEM_PROMPT_TEMPLATE.format(rule_text=self.rule_text.strip()),
            prompt=f"Transcript segments:\n\n{describe_segments(segments, classifications)}",
            schema=MOMENTS_SCHEMA,
            max_tokens=16000,
            effort="medium",
        )
        return parse_moments(response)
