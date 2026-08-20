from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class AuditLog:
    """Append-only JSONL audit log with a SHA-256 hash chain."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = ""
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return "0" * 64
        return json.loads(last)["entry_hash"]

    def append(self, event: str, details: dict) -> dict:
        record = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details,
            "prev_hash": self._last_hash(),
        }
        record["entry_hash"] = sha256(_canonical(record)).hexdigest()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def verify(self) -> bool:
        prev = "0" * 64
        if not self.path.exists():
            return True
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                entry_hash = record.pop("entry_hash")
                if record.get("prev_hash") != prev:
                    return False
                if sha256(_canonical(record)).hexdigest() != entry_hash:
                    return False
                prev = entry_hash
        return True
