"""Writes caption cues and the hook line as an ASS subtitle file that ffmpeg burns into the clip."""

from collections.abc import Sequence

from documenteveryday.captions.caption_cues import displayed_lines, wrap_caption_text
from documenteveryday.domain import CaptionCue

HOOK_ON_SCREEN_SECONDS = 3.5
HOOK_LINE_CHARACTERS = 20

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, \
MarginR, MarginV, Encoding
Style: Caption,Arial,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,560,1
Style: Translation,Arial,64,&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,-1,-1,0,0,100,100,0,0,1,5,2,2,60,60,560,1
Style: Hook,Arial,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_ass_timestamp(seconds: float) -> str:
    centiseconds = round(max(seconds, 0.0) * 100)
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def escape_ass_text(text: str) -> str:
    """Braces and backslashes are ASS control characters; spoken words never need them."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def dialogue_line(start_seconds: float, end_seconds: float, style: str, text: str) -> str:
    return (
        f"Dialogue: 0,{format_ass_timestamp(start_seconds)},{format_ass_timestamp(end_seconds)},"
        f"{style},,0,0,0,,{text}"
    )


def cue_markup(cue: CaptionCue) -> str:
    lines = [escape_ass_text(line) for line in displayed_lines(cue)]
    if cue.is_arabic and cue.english_translation:
        return lines[0] + r"\N{\rTranslation}" + r"\N".join(lines[1:])
    return r"\N".join(lines)


def hook_dialogue(hook_line: str, clip_duration: float) -> str:
    hook_markup = r"\N".join(
        escape_ass_text(line) for line in wrap_caption_text(hook_line, HOOK_LINE_CHARACTERS)
    )
    return dialogue_line(0.0, min(HOOK_ON_SCREEN_SECONDS, clip_duration), "Hook", hook_markup)


def render_ass_document(cues: Sequence[CaptionCue], hook_line: str, clip_duration: float) -> str:
    dialogue_lines = [hook_dialogue(hook_line, clip_duration)] if hook_line.strip() else []
    dialogue_lines += [
        dialogue_line(cue.start_seconds, cue.end_seconds, "Caption", cue_markup(cue)) for cue in cues
    ]
    return ASS_HEADER + "\n".join(dialogue_lines) + "\n"
