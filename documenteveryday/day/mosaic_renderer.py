"""Renders the day as one 9:16 video: every clip is a tile and they all play at once, each looping its few
chosen seconds. Title on top, the day's stats (or a count of things done) below.
"""

from pathlib import Path

from documenteveryday.captions.ass_subtitles import dialogue_line, escape_ass_text
from documenteveryday.day.day_plan import DayClip, DayPlan
from documenteveryday.day.mosaic_layout import Tile, grid_tiles
from documenteveryday.media.clip_renderer import VIDEO_ENCODER_ARGUMENTS
from documenteveryday.media.ffmpeg_tools import probe_duration_seconds, run_ffmpeg

WIDTH, HEIGHT, FPS = 1080, 1920, 30
HEADER_HEIGHT, FOOTER_HEIGHT = 190, 290
SUBTITLES_FILENAME = "day.ass"


DEFAULT_VIDEO_SECONDS = 6.0  # two passes of a 3-second tile; short enough to loop on Reels/TikTok


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
Style: Stats,Arial,64,&H0000C8FF,&H0000C8FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,50,50,0,1
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


def render_subtitles(plan: DayPlan, tiles: list[Tile], total: float) -> str:
    clips = plan.shown_clips
    footer_y = HEIGHT - FOOTER_HEIGHT // 2
    footer = escape_ass_text(plan.stats) if plan.stats else f"{len(clips)} things done today"
    lines = [
        dialogue_line(0, total, "Title", centered(HEADER_HEIGHT // 2) + escape_ass_text(plan.title)),
        dialogue_line(0, total, "Stats", centered(footer_y) + footer),
    ]
    lines += [
        dialogue_line(0, total, "Tile", tile_label_markup(clip, tile))
        for clip, tile in zip(clips, tiles, strict=True)
        if clip.label
    ]
    return ASS_HEADER + "\n".join(lines) + "\n"


def tile_filter(input_index: int, tile: Tile, play_seconds: float, total: float) -> str:
    loop_frames = max(1, round(play_seconds * FPS))
    return (
        f"[{input_index}:v]fps={FPS},scale={tile.width}:{tile.height}:force_original_aspect_ratio=increase,"
        f"crop={tile.width}:{tile.height},setsar=1,"
        f"trim=end_frame={loop_frames},loop=loop=-1:size={loop_frames}:start=0,"
        f"trim=duration={total:.3f},setpts=PTS-STARTPTS[tile{input_index}]"
    )


def build_ffmpeg_arguments(
    plan: DayPlan,
    day_directory: Path,
    output_path: Path,
    video_encoder: str,
    music_path: Path | None,
    total: float = DEFAULT_VIDEO_SECONDS,
) -> list[str]:
    clips = plan.shown_clips
    tiles = grid_tiles(len(clips), WIDTH, HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT, top=HEADER_HEIGHT)
    (day_directory / SUBTITLES_FILENAME).write_text(render_subtitles(plan, tiles, total), encoding="utf-8")

    input_arguments, filters = [], []
    previous = "base"
    filters.append(f"color=c=0x101010:s={WIDTH}x{HEIGHT}:r={FPS}:d={total:.3f}[base]")
    for index, (clip, tile) in enumerate(zip(clips, tiles, strict=True)):
        source = (day_directory / clip.file).resolve()
        play_seconds = max(0.5, min(clip.seconds, probe_duration_seconds(source) - clip.start))
        input_arguments += ["-ss", f"{clip.start:.3f}", "-t", f"{play_seconds:.3f}", "-i", str(source)]
        filters.append(tile_filter(index, tile, play_seconds, total))
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
    total_seconds: float = DEFAULT_VIDEO_SECONDS,
) -> Path:
    if not plan.shown_clips:
        raise ValueError("No clips to show: every clip is skipped or the folder has none.")
    arguments = build_ffmpeg_arguments(plan, day_directory, output_path, video_encoder, music_path, total_seconds)
    run_ffmpeg(arguments, working_directory=day_directory)
    return output_path
