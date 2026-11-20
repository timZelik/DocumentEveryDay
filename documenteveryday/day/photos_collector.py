"""Mac only: pulls every video recorded on a date out of Apple Photos into that day's folder.

iPhone clips reach the Mac's Photos library through iCloud Photos. Meta glasses clips get there too once
the Meta AI app saves them to the iPhone camera roll. Uses osxphotos (`pip install osxphotos`).
"""

import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path


def osxphotos_binary() -> str:
    binary = shutil.which("osxphotos")
    if binary is None:
        raise SystemExit("osxphotos is not installed: .venv/bin/pip install osxphotos")
    return binary


def collect_day_videos(day: date, day_directory: Path, album: str | None = None) -> None:
    day_directory.mkdir(parents=True, exist_ok=True)
    arguments = [
        osxphotos_binary(), "export", str(day_directory),
        "--only-movies",
        "--from-date", day.isoformat(), "--to-date", (day + timedelta(days=1)).isoformat(),
        "--download-missing",  # fetches iCloud originals that are not on the Mac yet
        "--update",            # re-running only copies new clips
        "--skip-edited",
    ]  # fmt: skip
    if album:
        arguments += ["--album", album]
    subprocess.run(arguments, check=True)


def save_to_photos(video_path: Path, album: str = "DocumentEveryDay") -> None:
    """Imports the finished video into Photos, so iCloud puts it in the iPhone camera roll for posting."""
    subprocess.run([osxphotos_binary(), "import", str(video_path.resolve()), "--album", album], check=True)
