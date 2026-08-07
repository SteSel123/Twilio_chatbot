#!/usr/bin/env python3
"""Automated PostgreSQL backup to local file (upload to S3/Azure in production)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", ".backups"))


def main() -> None:
    if not DATABASE_URL:
        print("DATABASE_URL not set — skipping backup")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    outfile = BACKUP_DIR / f"chatbot_{timestamp}.sql.gz"

    cmd = ["pg_dump", DATABASE_URL, "--no-owner", "--format=custom"]
    with outfile.open("wb") as f:
        dump = subprocess.run(cmd, stdout=f, check=False)
    if dump.returncode == 0:
        print(f"Backup written: {outfile}")
    else:
        print("Backup failed")
        outfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
