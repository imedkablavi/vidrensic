from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import uuid

from vidrensic.core.audit import AuditLog


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
CASE_SCHEMA_VERSION = 1


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
    def metadata_path(self) -> Path:
        return self.root / "case.json"

    @classmethod
    def create(
        cls,
        root: Path,
        case_id: str,
        *,
        examiner: str | None = None,
    ) -> "Case":
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(
                "case_id must be 1-80 characters using letters, numbers, '.', '_' or '-'"
            )
        root = root.expanduser().resolve()
        case_root = root / case_id
        case_root.mkdir(parents=True, exist_ok=False)

        for rel in (
            "evidence",
            "acquisitions",
            "derived/native",
            "derived/review",
            "work",
            "exports",
            "reports",
            "logs",
            "state",
        ):
            (case_root / rel).mkdir(parents=True)

        obj = cls(
            case_id=case_id,
            case_uuid=str(uuid.uuid4()),
            root=case_root,
            created_utc=datetime.now(timezone.utc).isoformat(),
            examiner=examiner,
        )
        obj._write_metadata()
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
    def load(cls, root: Path) -> "Case":
        root = root.expanduser().resolve()
        data = json.loads((root / "case.json").read_text(encoding="utf-8"))
        if data.get("schema_version") != CASE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported case schema version: {data.get('schema_version')!r}"
            )
        return cls(
            case_id=data["case_id"],
            case_uuid=data["case_uuid"],
            root=root,
            created_utc=data["created_utc"],
            examiner=data.get("examiner"),
            schema_version=data["schema_version"],
        )

    def _write_metadata(self) -> None:
        data = asdict(self)
        data["root"] = "."
        tmp = self.metadata_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.metadata_path)

    def safe_path(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes case root") from exc
        return candidate
