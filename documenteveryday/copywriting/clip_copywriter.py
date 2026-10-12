"""Writes each clip's hook line, title, post caption and hashtags in my voice."""

import re

from documenteveryday.domain import ClipCopy, ClipPlan
from documenteveryday.llm.claude_gateway import ClaudeGateway

MAXIMUM_HASHTAGS = 6
FALLBACK_TITLE_WORDS = 8

COPYWRITER_SYSTEM_PROMPT_TEMPLATE = """You write short-form video copy in one specific person's voice. \
Follow their style profile closely: their openers, slang, rhythm and sign-offs. Avoid generic influencer \
hype and anything the profile doesn't support.

<voice_profile>
{voice_profile}
</voice_profile>

Write:
- hook_line: on-screen text for the first 3 seconds, at most 8 words, that makes someone stop scrolling
- title: at most 60 characters
- post_caption: 1-3 sentences in their voice
- hashtags: 3-6 lowercase tags without the # sign
Everything must be true to what the clip's transcript says happens."""

COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "hook_line": {"type": "string"},
        "title": {"type": "string"},
        "post_caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook_line", "title", "post_caption", "hashtags"],
    "additionalProperties": False,
}


def normalize_hashtags(raw_hashtags: list[str]) -> tuple[str, ...]:
    cleaned = (re.sub(r"[^\w]", "", hashtag.lower()) for hashtag in raw_hashtags)
    return tuple(dict.fromkeys(hashtag for hashtag in cleaned if hashtag))[:MAXIMUM_HASHTAGS]


def fallback_copy(plan: ClipPlan, clip_text: str) -> ClipCopy:
    """Used when the AI budget is spent: plain, honest copy taken straight from what I said."""
    spoken_words = clip_text.split()
    return ClipCopy(
        hook_line="",
        title=" ".join(spoken_words[:FALLBACK_TITLE_WORDS]),
        post_caption=clip_text,
        hashtags=(plan.tag.value.replace("_", ""),),
    )


class ClaudeClipCopywriter:
    def __init__(self, gateway: ClaudeGateway, voice_profile: str):
        self.gateway = gateway
        self.voice_profile = voice_profile or "(No profile yet: write plainly and casually, first person.)"

    def write(self, plan: ClipPlan, clip_text: str, clip_id: int) -> ClipCopy:
        response = self.gateway.request_json(
            purpose="write_copy",
            system=COPYWRITER_SYSTEM_PROMPT_TEMPLATE.format(voice_profile=self.voice_profile.strip()),
            prompt=(
                f"Clip tag: {plan.tag.value}\nWhy it was picked: {plan.pick_reason}\n\nClip transcript:\n{clip_text}"
            ),
            schema=COPY_SCHEMA,
            max_tokens=4000,
            effort="low",
            clip_id=clip_id,
        )
        return ClipCopy(
            hook_line=response["hook_line"].strip(),
            title=response["title"].strip(),
            post_caption=response["post_caption"].strip(),
            hashtags=normalize_hashtags(response["hashtags"]),
        )
