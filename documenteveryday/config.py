"""Every knob in one place, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def environment_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


@dataclass(frozen=True)
class Settings:
    data_directory: Path
    rule_path: Path
    voice_profile_path: Path
    access_token: str
    claude_model: str
    batch_budget_dollars: float
    whisper_model: str
    video_encoder: str
    ntfy_server: str
    ntfy_topic: str
    public_base_url: str
    raw_footage_retention_days: int
    maximum_clips_per_batch: int
    minimum_clip_score: int

    @property
    def database_path(self) -> Path:
        return self.data_directory / "documenteveryday.sqlite3"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            data_directory=environment_path("DOCUMENTEVERYDAY_DATA_DIRECTORY", PROJECT_ROOT / "data"),
            rule_path=environment_path(
                "DOCUMENTEVERYDAY_RULE_PATH", PROJECT_ROOT / "rules/good_clip_rule.md"
            ),
            voice_profile_path=environment_path(
                "DOCUMENTEVERYDAY_VOICE_PROFILE_PATH", PROJECT_ROOT / "voice/my_voice.md"
            ),
            access_token=os.environ.get("DOCUMENTEVERYDAY_ACCESS_TOKEN", ""),
            claude_model=os.environ.get("DOCUMENTEVERYDAY_CLAUDE_MODEL", "claude-haiku-5-5"),
            batch_budget_dollars=float(os.environ.get("DOCUMENTEVERYDAY_BATCH_BUDGET_DOLLARS", "0.50")),
            whisper_model=os.environ.get("DOCUMENTEVERYDAY_WHISPER_MODEL", "small"),
            video_encoder=os.environ.get("DOCUMENTEVERYDAY_VIDEO_ENCODER", "libx264"),
            ntfy_server=os.environ.get("DOCUMENTEVERYDAY_NTFY_SERVER", "https://ntfy.sh"),
            ntfy_topic=os.environ.get("DOCUMENTEVERYDAY_NTFY_TOPIC", ""),
            public_base_url=os.environ.get("DOCUMENTEVERYDAY_PUBLIC_BASE_URL", "http://localhost:8000"),
            raw_footage_retention_days=int(
                os.environ.get("DOCUMENTEVERYDAY_RAW_FOOTAGE_RETENTION_DAYS", "5")
            ),
            maximum_clips_per_batch=int(os.environ.get("DOCUMENTEVERYDAY_MAXIMUM_CLIPS_PER_BATCH", "10")),
            minimum_clip_score=int(os.environ.get("DOCUMENTEVERYDAY_MINIMUM_CLIP_SCORE", "5")),
        )
