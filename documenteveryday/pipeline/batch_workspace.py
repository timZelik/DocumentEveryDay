"""Where one batch keeps its files on disk."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchWorkspace:
    data_directory: Path
    batch_id: int

    @property
    def root(self) -> Path:
        return self.data_directory / "batches" / str(self.batch_id)

    @property
    def uploads_directory(self) -> Path:
        return self.root / "uploads"

    @property
    def clips_directory(self) -> Path:
        return self.root / "clips"

    def transcript_path(self, source_video_id: int) -> Path:
        return self.root / "transcripts" / f"{source_video_id}.json"
