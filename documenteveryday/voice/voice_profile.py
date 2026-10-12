"""Builds voice/my_voice.md, a style profile of how I talk, from my own transcripts. Refreshed every batch."""

from collections.abc import Sequence
from pathlib import Path

from documenteveryday.domain import Transcript
from documenteveryday.llm.claude_gateway import ClaudeGateway

MAXIMUM_TRANSCRIPT_WORDS = 6000
EXCERPT_CHUNK_WORDS = 300

VOICE_PROFILE_SYSTEM_PROMPT = """You maintain a style profile of how one person talks, built only from \
transcripts of them talking to camera while they train, cook, study Arabic, and study tech. Other prompts \
will use this profile to write hooks and captions that sound like them, so it must be specific and quote \
their real words.

Write markdown with these sections:
## Openers (how they start a thought or a video)
## Phrases and slang (quoted, most characteristic first)
## Sentence length and rhythm
## Sign-offs
## Topics and vocabulary
## Writing in this voice: do / don't

Merge with the previous profile: keep what the new transcripts still support, add new patterns, drop \
anything they contradict. Never invent phrases. Stay under 400 words. Output only the profile."""


def evenly_spaced_excerpt(words: list[str], maximum_words: int, chunk_words: int) -> str:
    """Samples chunks across the whole evening instead of only its first minutes."""
    if len(words) <= maximum_words:
        return " ".join(words)
    chunk_count = max(2, maximum_words // chunk_words)
    last_start = len(words) - chunk_words
    starts = [round(position * last_start / (chunk_count - 1)) for position in range(chunk_count)]
    return "\n...\n".join(" ".join(words[start : start + chunk_words]) for start in starts)


def transcript_excerpt(transcripts: Sequence[Transcript]) -> str:
    spoken_words = [word.text for transcript in transcripts for word in transcript.words]
    return evenly_spaced_excerpt(spoken_words, MAXIMUM_TRANSCRIPT_WORDS, EXCERPT_CHUNK_WORDS)


class VoiceProfileBuilder:
    def __init__(self, gateway: ClaudeGateway, profile_path: Path):
        self.gateway = gateway
        self.profile_path = profile_path

    def current_profile(self) -> str:
        return self.profile_path.read_text() if self.profile_path.exists() else ""

    def refresh(self, transcripts: Sequence[Transcript]) -> str:
        excerpt = transcript_excerpt(transcripts)
        if not excerpt:
            return self.current_profile()
        profile = self.gateway.request_text(
            purpose="refresh_voice_profile",
            system=VOICE_PROFILE_SYSTEM_PROMPT,
            prompt=(
                f"<previous_profile>\n{self.current_profile() or '(none yet)'}\n</previous_profile>\n\n"
                f"<new_transcripts>\n{excerpt}\n</new_transcripts>"
            ),
            max_tokens=8000,
            effort="low",
        ).strip()
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(profile + "\n")
        return profile
