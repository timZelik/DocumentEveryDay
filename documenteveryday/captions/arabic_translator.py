"""Translates the few seconds of Egyptian Arabic into English, shown under the Arabic in the captions."""

from dataclasses import replace

from documenteveryday.domain import CaptionCue
from documenteveryday.llm.claude_gateway import ClaudeGateway

TRANSLATOR_SYSTEM_PROMPT = """You translate short Egyptian Arabic phrases spoken inside an English-language \
vlog into natural, casual English for on-screen captions. Translate the meaning, not word for word, and keep \
each translation under 40 characters. The Arabic comes from speech recognition and may be slightly wrong; \
use the surrounding English for context and give your best reading."""

TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"cue_index": {"type": "integer"}, "english": {"type": "string"}},
                "required": ["cue_index", "english"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


class ArabicCaptionTranslator:
    def __init__(self, gateway: ClaudeGateway):
        self.gateway = gateway
        self.english_by_arabic: dict[str, str] = {}  # retrims re-use translations instead of paying again

    def translate(self, cues: list[CaptionCue], context_text: str, clip_id: int) -> list[CaptionCue]:
        untranslated = {
            index: cue for index, cue in enumerate(cues) if cue.is_arabic and cue.text not in self.english_by_arabic
        }
        if untranslated:
            self.request_translations(untranslated, context_text, clip_id)
        return [
            replace(cue, english_translation=self.english_by_arabic.get(cue.text, "")) if cue.is_arabic else cue
            for cue in cues
        ]

    def request_translations(self, untranslated: dict[int, CaptionCue], context_text: str, clip_id: int) -> None:
        listed_cues = "\n".join(f"[{index}] {cue.text}" for index, cue in untranslated.items())
        response = self.gateway.request_json(
            purpose="translate_arabic",
            system=TRANSLATOR_SYSTEM_PROMPT,
            prompt=f"Surrounding speech:\n{context_text}\n\nArabic captions to translate:\n{listed_cues}",
            schema=TRANSLATION_SCHEMA,
            max_tokens=2000,
            effort="low",
            clip_id=clip_id,
        )
        for item in response["translations"]:
            if item["cue_index"] in untranslated:
                self.english_by_arabic[untranslated[item["cue_index"]].text] = item["english"].strip()
