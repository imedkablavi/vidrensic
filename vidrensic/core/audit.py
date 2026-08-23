from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import socket

from vidrensic import __version__


ZERO_HASH = "0" * 64
PRIVATE_FILE_MODE = 0o600


def _canonical(obj: dict) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    """Best-effort fsync of a directory entry after first file creation."""

    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class AuditVerificationError(ValueError):
    pass


class AuditLog:
    """Append-only JSONL audit log protected by a SHA-256 hash chain.

    The hash chain detects modification/reordering/truncation relative to a known
    final hash. It is not a substitute for a digital signature or external
    trusted timestamp.

    Linux advisory file locking is used so two Vidrensic processes cannot both
    read the same tail and create duplicate sequence numbers/hash parents.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _tail_from_handle(fh) -> tuple[int, str]:
        fh.seek(0)
        seq = 0
        tail_hash = ZERO_HASH
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            seq = int(record["seq"])
            tail_hash = str(record["entry_hash"])
        return seq, tail_hash

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, ZERO_HASH
        with self.path.open("r", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
            try:
                return self._tail_from_handle(fh)
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def append(
        self,
        event: str,
        details: dict,
        *,
        actor: str | None = None,
    ) -> dict:
        if not event or not isinstance(event, str):
            raise ValueError("event must be a non-empty string")

        existed = self.path.exists()
        with self.path.open("a+", encoding="utf-8") as fh:
            # Tighten permissions for both newly-created and legacy audit logs.
            os.chmod(self.path, PRIVATE_FILE_MODE)
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                last_seq, prev_hash = self._tail_from_handle(fh)
                record = {
                    "seq": last_seq + 1,
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    "actor": actor,
                    "host": socket.gethostname(),
                    "pid": os.getpid(),
                    "vidrensic_version": __version__,
                    "details": details,
                    "prev_hash": prev_hash,
                }
                record["entry_hash"] = sha256(_canonical(record)).hexdigest()

                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

        if not existed:
            _fsync_directory(self.path.parent)
        return record

    def verify(self, *, expected_tail_hash: str | None = None) -> tuple[bool, str]:
        prev = ZERO_HASH
        expected_seq = 1
        if not self.path.exists():
            ok = expected_tail_hash in (None, ZERO_HASH)
            return ok, ZERO_HASH

        with self.path.open("r", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
            try:
                for line_no, line in enumerate(fh, start=1):
                    if not line.strip():
                        continue
                    try:
                        stored = json.loads(line)
                    except json.JSONDecodeError:
                        return False, f"invalid JSON at line {line_no}"
                    entry_hash = stored.get("entry_hash")
                    if stored.get("seq") != expected_seq:
                        return False, f"sequence mismatch at line {line_no}"
                    if stored.get("prev_hash") != prev:
                        return False, f"previous-hash mismatch at line {line_no}"
                    unsigned = dict(stored)
                    unsigned.pop("entry_hash", None)
                    calculated = sha256(_canonical(unsigned)).hexdigest()
                    if calculated != entry_hash:
                        return False, f"entry-hash mismatch at line {line_no}"
                    prev = str(entry_hash)
                    expected_seq += 1
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

        if expected_tail_hash is not None and prev != expected_tail_hash:
            return False, "tail hash does not match expected value"
        return True, prev

    def require_valid(self, *, expected_tail_hash: str | None = None) -> str:
        ok, result = self.verify(expected_tail_hash=expected_tail_hash)
        if not ok:
            raise AuditVerificationError(result)
        return result
