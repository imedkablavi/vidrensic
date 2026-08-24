from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import os
import re
import uuid

from vidrensic.core.audit import AuditLog
from vidrensic.core.jobs import JobStore
from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
CASE_SCHEMA_VERSION = 1
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_CASE_METADATA_BYTES = 1024 * 1024
MAX_CASE_METADATA_STRING_CHARS = 16 * 1024


@dataclass(frozen=True)
class Case:
    case_id: str
    case_uuid: str
    root: Path
    created_utc: str
    examiner: str | None
    schema_version: int = CASE_SCHEMA_VERSION

    @property
    def audit(self) -> AuditLog:
        return AuditLog(self.root / "logs" / "audit.jsonl")

    @property
    def jobs(self) -> JobStore:
        return JobStore(self.root / "state" / "jobs.sqlite3")

    @property
    def metadata_path(self) -> Path:
        return self.root / "case.json"

    @classmethod
    def create(
        cls,
        root: Path,
        case_id: str,
        *,
        examiner: str | None = None,
    ) -> Case:
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(
                "case_id must be 1-80 characters using letters, numbers, '.', '_' or '-'"
            )
        if examiner is not None:
            if not isinstance(examiner, str) or len(examiner) > MAX_CASE_METADATA_STRING_CHARS:
                raise ValueError(
                    f"examiner must be a string of at most {MAX_CASE_METADATA_STRING_CHARS} characters"
                )
        root = root.expanduser().resolve()
        case_root = root / case_id
        case_root.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=False)
        os.chmod(case_root, PRIVATE_DIR_MODE)

        # Create every case-owned directory explicitly so an intermediate path
        # (notably ``derived``) cannot inherit a permissive default mode.
        for rel in (
            "evidence",
            "acquisitions",
            "derived",
            "derived/native",
            "derived/review",
            "work",
            "exports",
            "reports",
            "logs",
            "state",
        ):
            directory = case_root / rel
            directory.mkdir(mode=PRIVATE_DIR_MODE, parents=False, exist_ok=False)
            os.chmod(directory, PRIVATE_DIR_MODE)

        obj = cls(
            case_id=case_id,
            case_uuid=str(uuid.uuid4()),
            root=case_root,
            created_utc=datetime.now(UTC).isoformat(),
            examiner=examiner,
        )
        obj._write_metadata()
        # Initialize job DB immediately so schema failures are discovered while
        # creating the case, not during a later long-running operation.
        _ = obj.jobs
        obj.audit.append(
            "case.created",
            {
                "case_id": obj.case_id,
                "case_uuid": obj.case_uuid,
                "root": str(obj.root),
                "schema_version": obj.schema_version,
            },
            actor=examiner,
        )
        return obj

    @classmethod
    def load(cls, root: Path) -> Case:
        root = root.expanduser().resolve()
        metadata_path = root / "case.json"
        if metadata_path.is_symlink():
            raise ValueError("case metadata may not be a symlink")
        try:
            data = load_bounded_json(
                metadata_path,
                max_bytes=MAX_CASE_METADATA_BYTES,
                max_depth=16,
                max_nodes=1024,
                max_string_chars=MAX_CASE_METADATA_STRING_CHARS,
                label="case metadata",
            )
        except BoundedJSONError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(data, dict):
            raise ValueError("case metadata must be a JSON object")
        if data.get("schema_version") != CASE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported case schema version: {data.get('schema_version')!r}"
            )

        case_id = data.get("case_id")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise ValueError("case metadata contains an invalid case_id")

        case_uuid = data.get("case_uuid")
        if not isinstance(case_uuid, str):
            raise ValueError("case metadata contains an invalid case_uuid")
        try:
            normalized_uuid = str(uuid.UUID(case_uuid))
        except (ValueError, AttributeError) as exc:
            raise ValueError("case metadata contains an invalid case_uuid") from exc
        if normalized_uuid != case_uuid.lower():
            raise ValueError("case metadata case_uuid must use canonical UUID text")

        created_utc = data.get("created_utc")
        if not isinstance(created_utc, str):
            raise ValueError("case metadata contains an invalid created_utc")
        try:
            created = datetime.fromisoformat(created_utc)
        except ValueError as exc:
            raise ValueError("case metadata created_utc is not valid ISO-8601") from exc
        if created.tzinfo is None:
            raise ValueError("case metadata created_utc must include a timezone")

        examiner = data.get("examiner")
        if examiner is not None and not isinstance(examiner, str):
            raise ValueError("case metadata examiner must be a string or null")

        return cls(
            case_id=case_id,
            case_uuid=case_uuid,
            root=root,
            created_utc=created_utc,
            examiner=examiner,
            schema_version=CASE_SCHEMA_VERSION,
        )

    def _write_metadata(self) -> None:
        data = asdict(self)
        data["root"] = "."
        tmp = self.metadata_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, PRIVATE_FILE_MODE)
        tmp.replace(self.metadata_path)
        os.chmod(self.metadata_path, PRIVATE_FILE_MODE)

    def safe_path(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes case root") from exc
        return candidate
