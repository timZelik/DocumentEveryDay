"""Renders the day as one 9:16 video: tiles pop in one by one in the order the day happened, each looping
its few chosen seconds, until the whole puzzle plays at once. Title on top, the newest thing done below.
"""

from dataclasses import dataclass
from pathlib import Path

from documenteveryday.captions.ass_subtitles import dialogue_line, escape_ass_text
from documenteveryday.day.day_plan import DayClip, DayPlan
from documenteveryday.day.mosaic_layout import Tile, grid_tiles
from documenteveryday.media.clip_renderer import VIDEO_ENCODER_ARGUMENTS
from documenteveryday.media.ffmpeg_tools import probe_duration_seconds, run_ffmpeg

WIDTH, HEIGHT, FPS = 1080, 1920, 30
HEADER_HEIGHT, FOOTER_HEIGHT = 190, 290
FADE_SECONDS = 0.25
SUBTITLES_FILENAME = "day.ass"


@dataclass(frozen=True)
class MosaicTiming:
    stagger_seconds: float
    hold_seconds: float

    @classmethod
    def for_tile_count(cls, tile_count: int) -> "MosaicTiming":
        """About 12 seconds of build-up however many clips there are, then the full puzzle."""
        return cls(stagger_seconds=min(1.0, max(0.45, 12.0 / max(tile_count, 1))), hold_seconds=4.0)

    def appear_at(self, index: int) -> float:
        return round(index * self.stagger_seconds, 3)

    def total_seconds(self, tile_count: int) -> float:
        return self.appear_at(tile_count - 1) + self.hold_seconds


ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, \
MarginR, MarginV, Encoding
Style: Title,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1
Style: Footer,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,50,50,0,1
Style: Stats,Arial,60,&H0000C8FF,&H0000C8FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,50,50,0,1
Style: Tile,Arial,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,6,0,1,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def tile_label_markup(clip: DayClip, tile: Tile) -> str:
    font_size = max(18, min(40, tile.width // 9))
    text = escape_ass_text(clip.label)
    if clip.detail:
        text += r"\N{\fs" + str(round(font_size * 0.8)) + "}" + escape_ass_text(clip.detail)
    return r"{\an1\pos(" + f"{tile.x + 10},{tile.y + tile.height - 10}" + r")\fs" + str(font_size) + "}" + text


def centered(y: int) -> str:
    return r"{\pos(" + f"{WIDTH // 2},{y}" + ")}"


def render_subtitles(plan: DayPlan, tiles: list[Tile], timing: MosaicTiming) -> str:
    clips = plan.shown_clips
    total = timing.total_seconds(len(clips))
    footer_y = HEIGHT - FOOTER_HEIGHT // 2
    lines = [dialogue_line(0, total, "Title", centered(HEADER_HEIGHT // 2) + escape_ass_text(plan.title))]
    for index, (clip, tile) in enumerate(zip(clips, tiles, strict=True)):
        appear = timing.appear_at(index)
        if clip.label:
            lines.append(dialogue_line(appear + FADE_SECONDS, total, "Tile", tile_label_markup(clip, tile)))
            next_appear = timing.appear_at(index + 1) if index + 1 < len(clips) else appear + 1.0
            footer_text = "✓ " + escape_ass_text(clip.label)
            lines.append(dialogue_line(appear, next_appear, "Footer", centered(footer_y) + footer_text))
    finale_start = timing.appear_at(len(clips) - 1) + 1.0
    finale = escape_ass_text(plan.stats) if plan.stats else f"{len(clips)} things done today"
    lines.append(dialogue_line(finale_start, total, "Stats", centered(footer_y) + finale))
    return ASS_HEADER + "\n".join(lines) + "\n"


def tile_filter(input_index: int, tile: Tile, appear: float, play_seconds: float, total: float) -> str:
    loop_frames = max(1, round(play_seconds * FPS))
    return (
        f"[{input_index}:v]fps={FPS},scale={tile.width}:{tile.height}:force_original_aspect_ratio=increase,"
        f"crop={tile.width}:{tile.height},setsar=1,format=yuva420p,"
        f"trim=end_frame={loop_frames},loop=loop=-1:size={loop_frames}:start=0,"
        f"trim=duration={total - appear:.3f},setpts=PTS-STARTPTS+{appear:.3f}/TB,"
        f"fade=t=in:st={appear:.3f}:d={FADE_SECONDS}:alpha=1[tile{input_index}]"
    )


def build_ffmpeg_arguments(
    plan: DayPlan, day_directory: Path, output_path: Path, video_encoder: str, music_path: Path | None
) -> list[str]:
    clips = plan.shown_clips
    timing = MosaicTiming.for_tile_count(len(clips))
    total = timing.total_seconds(len(clips))
    tiles = grid_tiles(len(clips), WIDTH, HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT, top=HEADER_HEIGHT)
    (day_directory / SUBTITLES_FILENAME).write_text(render_subtitles(plan, tiles, timing), encoding="utf-8")

    input_arguments, filters = [], []
    previous = "base"
    filters.append(f"color=c=0x101010:s={WIDTH}x{HEIGHT}:r={FPS}:d={total:.3f}[base]")
    for index, (clip, tile) in enumerate(zip(clips, tiles, strict=True)):
        source = (day_directory / clip.file).resolve()
        play_seconds = max(0.5, min(clip.seconds, probe_duration_seconds(source) - clip.start))
        input_arguments += ["-ss", f"{clip.start:.3f}", "-t", f"{play_seconds:.3f}", "-i", str(source)]
        filters.append(tile_filter(index, tile, timing.appear_at(index), play_seconds, total))
        filters.append(f"[{previous}][tile{index}]overlay=x={tile.x}:y={tile.y}:eof_action=pass[stack{index}]")
        previous = f"stack{index}"
    filters.append(f"[{previous}]subtitles={SUBTITLES_FILENAME},format=yuv420p[video]")

    audio_arguments = ["-an"]
    if music_path is not None:
        input_arguments += ["-i", str(music_path.resolve())]
        fade_out = f"afade=t=out:st={total - 1.5:.3f}:d=1.5"
        audio_arguments = ["-map", f"{len(clips)}:a:0", "-c:a", "aac", "-b:a", "192k", "-af", fade_out]
    return [
        "-y", *input_arguments,
        "-filter_complex", ";".join(filters),
        "-map", "[video]", *audio_arguments,
        "-t", f"{total:.3f}",
        *VIDEO_ENCODER_ARGUMENTS[video_encoder],
        "-r", str(FPS), "-movflags", "+faststart",
        str(output_path.resolve()),
    ]  # fmt: skip


def render_day_mosaic(
    plan: DayPlan,
    day_directory: Path,
    output_path: Path,
    video_encoder: str = "libx264",
    music_path: Path | None = None,
) -> Path:
    if not plan.shown_clips:
        raise ValueError("No clips to show: every clip is skipped or the folder has none.")
    arguments = build_ffmpeg_arguments(plan, day_directory, output_path, video_encoder, music_path)
    run_ffmpeg(arguments, working_directory=day_directory)
    return output_path
