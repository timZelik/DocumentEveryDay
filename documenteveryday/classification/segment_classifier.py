"""Tags each segment with what I was doing. The SegmentClassifier Protocol is the seam for benchmarking
another tagger (e.g. TypeSafe's Jev) against Claude on hand-labelled segments later."""

from collections.abc import Sequence
from typing import Protocol

from documenteveryday.domain import Segment, SegmentClassification, SegmentTag
from documenteveryday.llm.claude_gateway import ClaudeGateway
from documenteveryday.llm.prompt_formatting import describe_segments


class SegmentClassifier(Protocol):
    def classify(self, segments: Sequence[Segment]) -> dict[int, SegmentClassification]: ...


CLASSIFIER_SYSTEM_PROMPT = """You tag segments of a transcript. The speaker films their own after-work \
sessions and talks while filming. Give every segment exactly one tag:
- training: working out, lifting, cardio, mobility, talking about a workout
- food_prep: cooking, meal prep, groceries, talking about food they're making
- arabic: studying Arabic (vocabulary, grammar, practising phrases), including Egyptian dialect
- tech_study: programming, AI, reading docs, building or debugging software
- other: anything else, including camera setup and small talk
Judge by what is being done or discussed, not by single words. The reason is one short clause a \
reviewer can read at a glance."""

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_index": {"type": "integer"},
                    "tag": {"type": "string", "enum": [tag.value for tag in SegmentTag]},
                    "reason": {"type": "string"},
                },
                "required": ["segment_index", "tag", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classifications"],
    "additionalProperties": False,
}


def parse_classifications(response: dict, segments: Sequence[Segment]) -> dict[int, SegmentClassification]:
    """Keeps only indices that exist; any segment the model skipped is tagged 'other' and says so."""
    known_indices = {segment.index for segment in segments}
    classifications = {
        item["segment_index"]: SegmentClassification(SegmentTag(item["tag"]), item["reason"])
        for item in response["classifications"]
        if item["segment_index"] in known_indices
    }
    missing = SegmentClassification(SegmentTag.OTHER, "Not tagged by the classifier.")
    return {index: classifications.get(index, missing) for index in sorted(known_indices)}


class ClaudeSegmentClassifier:
    def __init__(self, gateway: ClaudeGateway):
        self.gateway = gateway

    def classify(self, segments: Sequence[Segment]) -> dict[int, SegmentClassification]:
        if not segments:
            return {}
        response = self.gateway.request_json(
            purpose="classify_segments",
            system=CLASSIFIER_SYSTEM_PROMPT,
            prompt=f"Tag every segment below.\n\n{describe_segments(segments)}",
            schema=CLASSIFICATION_SCHEMA,
            max_tokens=16000,
            effort="low",
        )
        return parse_classifications(response, segments)
