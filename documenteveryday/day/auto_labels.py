"""Optional, cheap AI: one Claude Haiku call per day names every tile from a single small frame each.

Roughly 300 input tokens per clip, so a 15-clip day costs well under a cent. Frames are 320px wide JPEGs
taken from the middle of each chosen moment. Without an API key the labels just stay blank for you to fill.
"""

import base64
import json
import re
import tempfile
from pathlib import Path

from documenteveryday.day.day_plan import DayClip
from documenteveryday.media.ffmpeg_tools import run_ffmpeg

LABEL_PROMPT = (
    "These are frames from short clips I recorded today, in order, for a 'what I did today' video. "
    "For each frame give a 1-4 word past-tense label of the activity, like 'Put shoes on', 'Ran', "
    "'Folded laundry', 'Vacuumed', 'Studied Arabic', 'Dinner'. Reply with only a JSON array of strings, "
    "one per frame, same order."
)


def middle_frame_jpeg(video_path: Path, at_seconds: float, output_path: Path) -> bytes:
    run_ffmpeg(["-y", "-ss", f"{at_seconds:.2f}", "-i", str(video_path.resolve()), "-frames:v", "1",
                "-vf", "scale=320:-2", "-q:v", "6", str(output_path)])  # fmt: skip
    return output_path.read_bytes()


def parse_labels(text: str, expected: int) -> list[str]:
    """Takes the first JSON array of strings in the reply; anything unusable leaves labels blank."""
    labels: list = []
    for candidate in re.findall(r"\[[^\[\]]*\]", text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list) and parsed:
            labels = parsed
            break
    labels = [str(label).strip() for label in labels][:expected]
    return labels + [""] * (expected - len(labels))


def label_clips(clips: list[DayClip], day_directory: Path, client, model: str) -> tuple[list[str], dict]:
    content = []
    with tempfile.TemporaryDirectory() as scratch:
        for index, clip in enumerate(clips):
            frame = middle_frame_jpeg(
                day_directory / clip.file, clip.start + clip.seconds / 2, Path(scratch) / f"{index}.jpg"
            )
            content.append({"type": "text", "text": f"Frame {index + 1}:"})
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(frame).decode()}}
            )  # fmt: skip
    content.append({"type": "text", "text": LABEL_PROMPT})
    response = client.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": content}])
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return parse_labels(text, len(clips)), usage
