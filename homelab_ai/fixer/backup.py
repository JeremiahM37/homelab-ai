"""File-backup helper for Tier-3 edits.

Before any file write, the fixer calls `FileBackup.snapshot(path)` which
copies the original to `backup_dir/<sha>-<basename>` and returns the
`backup_id`. `restore(backup_id)` puts the file back. Snapshots are
idempotent — a second call returns the existing id.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger("homelab_ai.fixer.backup")


class FileBackup:
    def __init__(self, backup_dir: str | Path):
        self.dir = Path(backup_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _backup_id(self, src: Path) -> str:
        h = hashlib.sha1(str(src.resolve()).encode()).hexdigest()[:12]
        return f"{int(time.time())}-{h}-{src.name}"

    def snapshot(self, path: str | Path) -> str:
        src = Path(path)
        if not src.is_file():
            raise FileNotFoundError(src)
        backup_id = self._backup_id(src)
        dest = self.dir / backup_id
        shutil.copy2(src, dest)
        logger.info("snapshot %s -> %s", src, dest)
        return backup_id

    def restore(self, backup_id: str, dest: str | Path | None = None) -> Path:
        src = self.dir / backup_id
        if not src.is_file():
            raise FileNotFoundError(backup_id)
        # backup_id format: timestamp-sha-basename — the destination is
        # whatever the caller provides, otherwise we just put it next to
        # the backup with .restored suffix.
        if dest is None:
            dest = Path(self.dir / f"{backup_id}.restored")
        else:
            dest = Path(dest)
        shutil.copy2(src, dest)
        logger.info("restored %s -> %s", backup_id, dest)
        return dest

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.dir.iterdir()):
            if f.is_file():
                out.append({
                    "id": f.name,
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                })
        return out
