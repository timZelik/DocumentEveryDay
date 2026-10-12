"""Seam for where a clip's audio comes from.

Mode A (built): my own narration, so no replacement track. Mode B (later): a voiceover I record from an
AI-written script. Mode C (later): that script read by a cloned voice. Both return an audio file path."""

from pathlib import Path
from typing import Protocol

from documenteveryday.domain import ClipCopy, ClipPlan


class VoiceoverProvider(Protocol):
    def voiceover_for(self, plan: ClipPlan, clip_copy: ClipCopy) -> Path | None: ...


class NaturalNarration:
    def voiceover_for(self, plan: ClipPlan, clip_copy: ClipCopy) -> Path | None:
        return None
