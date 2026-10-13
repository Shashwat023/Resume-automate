"""
Local filesystem implementation of ports.ResumeStoragePort. Extracted
verbatim from what was inline in api/resume.py's upload/delete handlers.
This is the port's only implementation today; swapping to S3/GDrive later
means adding one new class here, not touching resume_service.py or the
route — that's the concrete payoff of the port boundary.
"""

import re
from pathlib import Path
from urllib.parse import quote

from app.ports import SavedFile


def safe_filename(filename: str) -> str:
    """Strip any directory part and unsafe characters from an uploaded name."""
    name = re.split(r"[\\/]", filename or "")[-1].strip().strip(".")
    name = re.sub(r"[^\w.\- ]", "_", name).strip()
    return name or "resume"


class LocalFilesystemStorage:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    async def save(self, profile_id: int, filename: str, contents: bytes) -> SavedFile:
        profile_dir = self._base_dir / str(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(filename)
        dest_path = profile_dir / filename
        dest_path.write_bytes(contents)
        return SavedFile(
            file_path=str(dest_path),
            resume_url=f"/storage/resumes/{profile_id}/{quote(filename)}",
        )

    async def delete(self, file_path: str) -> None:
        path = Path(file_path)
        if path.exists():
            path.unlink()
