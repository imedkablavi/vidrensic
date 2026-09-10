from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import os
import uuid

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import PRIVATE_FILE_MODE, atomic_write_private_json


SCHEMA_VERSION = 1
MAX_REASON_CHARS = 2048
MAX_PLAN_ENTRIES = 256
ALLOWED_ROOTS = ("derived", "work")


class DeletionPlanError(RuntimeError):
    """Raised when a deletion plan cannot be created or executed safely."""


@dataclass(frozen=True)
class DeletionTarget:
    target_id: str
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str
    kind: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "path": str(self.path),
        }


@dataclass(frozen=True)
class DeletionPlan:
    plan_id: str
    case_root: Path
    created_utc: str
    actor: str | None
    targets: tuple[DeletionTarget, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "case_root": str(self.case_root),
            "created_utc": self.created_utc,
            "actor": self.actor,
            "destructive": False,
            "targets": [target.to_dict() for target in self.targets],
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _allowed_target(case_root: Path, path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise DeletionPlanError("deletion target may not be a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise DeletionPlanError("deletion target must be a regular file")
    try:
        relative = resolved.relative_to(case_root)
    except ValueError as exc:
        raise DeletionPlanError("deletion target must be inside the case root") from exc
    if not relative.parts or relative.parts[0] not in ALLOWED_ROOTS:
        raise DeletionPlanError("deletion target is outside the derived/work safety boundary")
    return resolved


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise DeletionPlanError("deletion reason is required")
    reason = reason.strip()
    if len(reason) > MAX_REASON_CHARS:
        raise DeletionPlanError(f"deletion reason exceeds {MAX_REASON_CHARS} characters")
    return reason


def create_deletion_plan(
    case_root: Path,
    targets: list[Path],
    *,
    actor: str | None = None,
    reason: str,
) -> DeletionPlan:
    root = case_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise DeletionPlanError("case root must be a directory")
    if not 1 <= len(targets) <= MAX_PLAN_ENTRIES:
        raise DeletionPlanError(f"deletion plan must contain 1-{MAX_PLAN_ENTRIES} targets")
    normalized_reason = _validate_reason(reason)
    entries: list[DeletionTarget] = []
    seen: set[str] = set()
    for target in targets:
        resolved = _allowed_target(root, target)
        relative = resolved.relative_to(root)
        key = relative.as_posix()
        if key in seen:
            raise DeletionPlanError(f"duplicate deletion target: {relative}")
        seen.add(key)
        hashes = forensic_hashes_stable(resolved)
        kind = relative.parts[0]
        entries.append(
            DeletionTarget(
                target_id=str(uuid.uuid4()),
                path=resolved,
                relative_path=key,
                size_bytes=resolved.stat().st_size,
                sha256=hashes.sha256,
                kind=kind,
                reason=normalized_reason,
            )
        )
    return DeletionPlan(
        plan_id=str(uuid.uuid4()),
        case_root=root,
        created_utc=datetime.now(UTC).isoformat(),
        actor=actor,
        targets=tuple(entries),
    )


def _load_plan(path: Path, case_root: Path) -> DeletionPlan:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise DeletionPlanError("deletion plan may not be a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise DeletionPlanError("deletion plan must be a regular file")
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DeletionPlanError(f"unable to read deletion plan: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise DeletionPlanError("unsupported deletion plan schema")
    plan_root = Path(str(data.get("case_root", ""))).expanduser().resolve()
    expected_root = case_root.expanduser().resolve(strict=True)
    if plan_root != expected_root:
        raise DeletionPlanError("deletion plan is bound to a different case root")
    plan_id = data.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        raise DeletionPlanError("deletion plan has an invalid plan_id")
    created_utc = data.get("created_utc")
    if not isinstance(created_utc, str):
        raise DeletionPlanError("deletion plan has an invalid timestamp")
    actor = data.get("actor")
    if actor is not None and not isinstance(actor, str):
        raise DeletionPlanError("deletion plan actor must be a string or null")
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not 1 <= len(raw_targets) <= MAX_PLAN_ENTRIES:
        raise DeletionPlanError("deletion plan has an invalid target collection")
    targets: list[DeletionTarget] = []
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise DeletionPlanError("deletion plan target is not an object")
        target_id = raw.get("target_id")
        relative = raw.get("relative_path")
        sha256 = raw.get("sha256")
        size_bytes = raw.get("size_bytes")
        kind = raw.get("kind")
        reason = raw.get("reason")
        if not all(isinstance(value, str) for value in (target_id, relative, sha256, kind, reason)):
            raise DeletionPlanError("deletion plan target contains invalid text")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise DeletionPlanError("deletion plan target contains invalid size")
        if len(sha256) != 64:
            raise DeletionPlanError("deletion plan target contains an invalid SHA-256")
        try:
            int(sha256, 16)
        except ValueError as exc:
            raise DeletionPlanError("deletion plan target contains an invalid SHA-256") from exc
        target_path = _allowed_target(expected_root, expected_root / relative)
        if target_path.relative_to(expected_root).as_posix() != relative:
            raise DeletionPlanError("deletion plan target path normalization mismatch")
        targets.append(
            DeletionTarget(
                target_id=target_id,
                path=target_path,
                relative_path=relative,
                size_bytes=size_bytes,
                sha256=sha256.lower(),
                kind=kind,
                reason=_validate_reason(reason),
            )
        )
    return DeletionPlan(
        plan_id=plan_id,
        case_root=expected_root,
        created_utc=created_utc,
        actor=actor,
        targets=tuple(targets),
    )


def _append_tombstone(path: Path, result: dict[str, object]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, PRIVATE_FILE_MODE)
    except OSError as exc:
        raise DeletionPlanError(f"unable to open tombstone log safely: {exc}") from exc
    try:
        payload = (json.dumps(result, sort_keys=True) + "\n").encode("utf-8")
        os.write(fd, payload)
        os.fsync(fd)
        os.fchmod(fd, PRIVATE_FILE_MODE)
    finally:
        os.close(fd)


def execute_deletion_plan(
    case_root: Path,
    plan_path: Path,
    *,
    tombstone_path: Path | None = None,
    actor: str | None = None,
) -> list[dict[str, object]]:
    root = case_root.expanduser().resolve(strict=True)
    plan = _load_plan(plan_path, root)
    plan_resolved = plan_path.expanduser().resolve(strict=True)
    plan_relative = plan_resolved.relative_to(root).as_posix()
    for target in plan.targets:
        if target.relative_path == plan_relative:
            raise DeletionPlanError("deletion plan may not delete itself")

    tombstones = tombstone_path or (root / "state" / "deletion_tombstones.jsonl")
    tombstones = tombstones.expanduser()
    if tombstones.is_symlink():
        raise DeletionPlanError("tombstone log may not be a symlink")
    tombstone_resolved = tombstones.resolve()
    try:
        tombstone_resolved.relative_to(root)
    except ValueError as exc:
        raise DeletionPlanError("tombstone log must be inside the case root") from exc
    tombstone_relative = tombstone_resolved.relative_to(root).as_posix()
    if tombstone_relative in {target.relative_path for target in plan.targets}:
        raise DeletionPlanError("tombstone log may not overlap a deletion target")
    tombstone_resolved.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(tombstone_resolved.parent, 0o700)

    now = datetime.now(UTC).isoformat()
    checked: list[DeletionTarget] = []
    for target in plan.targets:
        path = target.path
        if path.is_symlink():
            raise DeletionPlanError(f"target became a symlink: {target.relative_path}")
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise DeletionPlanError(f"target is no longer a regular file: {target.relative_path}")
        if resolved.relative_to(root).as_posix() != target.relative_path:
            raise DeletionPlanError(f"target path no longer matches the plan: {target.relative_path}")
        current = forensic_hashes_stable(resolved)
        if current.sha256 != target.sha256:
            raise DeletionPlanError(f"target SHA-256 no longer matches the plan: {target.relative_path}")
        if resolved.stat().st_size != target.size_bytes:
            raise DeletionPlanError(f"target size no longer matches the plan: {target.relative_path}")
        checked.append(target)

    results: list[dict[str, object]] = []
    for target in checked:
        path = target.path
        try:
            if path.is_symlink():
                raise DeletionPlanError("target became a symlink after preflight")
            resolved = path.resolve(strict=True)
            if resolved.relative_to(root).as_posix() != target.relative_path:
                raise DeletionPlanError("target path no longer matches the plan after preflight")
            current = forensic_hashes_stable(resolved)
            if current.sha256 != target.sha256:
                raise DeletionPlanError("target SHA-256 no longer matches the plan after preflight")
            if resolved.stat().st_size != target.size_bytes:
                raise DeletionPlanError("target size no longer matches the plan after preflight")
            resolved.unlink()
        except (OSError, ValueError, DeletionPlanError) as exc:
            raise DeletionPlanError(f"deletion stopped at {target.relative_path}: {exc}") from exc
        result = {
            "plan_id": plan.plan_id,
            "target_id": target.target_id,
            "relative_path": target.relative_path,
            "expected_sha256": target.sha256,
            "observed_sha256": current.sha256,
            "size_bytes": target.size_bytes,
            "status": "deleted",
            "timestamp_utc": now,
            "actor": actor or plan.actor,
            "reason": target.reason,
        }
        results.append(result)
        _append_tombstone(tombstones, result)
    return results
