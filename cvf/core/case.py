from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json


@dataclass(frozen=True)
class Case:
    case_id: str
    root: Path
    created_utc: str

    @classmethod
    def create(cls, root: Path, case_id: str) -> "Case":
        case_root = root / case_id
        case_root.mkdir(parents=True, exist_ok=False)
        for name in ("evidence", "acquisitions", "work", "exports", "reports", "logs"):
            (case_root / name).mkdir()
        obj = cls(case_id=case_id, root=case_root,
                  created_utc=datetime.now(timezone.utc).isoformat())
        (case_root / "case.json").write_text(
            json.dumps({**asdict(obj), "root": str(obj.root)}, indent=2) + "\n",
            encoding="utf-8",
        )
        return obj
