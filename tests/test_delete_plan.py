from pathlib import Path

import pytest

from vidrensic.core.case import Case
from vidrensic.core.delete_plan import DeletionPlanError, create_deletion_plan, execute_deletion_plan
from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic import review_cli


def _case(tmp_path: Path) -> Case:
    return Case.create(tmp_path, "CASE-DELETE", examiner="examiner")


def test_deletion_plan_is_non_destructive_and_hash_bound(tmp_path: Path) -> None:
    case = _case(tmp_path)
    target = case.root / "derived" / "review" / "proxy.mp4"
    target.write_bytes(b"proxy-data")

    plan = create_deletion_plan(
        case.root,
        [target],
        actor=case.examiner,
        reason="discarded review proxy",
    )

    assert target.exists()
    assert plan.to_dict()["destructive"] is False
    assert plan.targets[0].sha256 == forensic_hashes_stable(target).sha256
    assert plan.targets[0].size_bytes == target.stat().st_size


def test_deletion_plan_rejects_evidence_and_symlinks(tmp_path: Path) -> None:
    case = _case(tmp_path)
    evidence = case.root / "evidence" / "original.bin"
    evidence.write_bytes(b"immutable")
    with pytest.raises(DeletionPlanError):
        create_deletion_plan(case.root, [evidence], reason="bad target")

    derived = case.root / "derived" / "review" / "proxy.mp4"
    derived.write_bytes(b"proxy")
    link = case.root / "derived" / "review" / "link.mp4"
    link.symlink_to(derived)
    with pytest.raises(DeletionPlanError):
        create_deletion_plan(case.root, [link], reason="symlink target")


def test_execute_requires_matching_hash_and_writes_tombstone(tmp_path: Path) -> None:
    case = _case(tmp_path)
    target = case.root / "derived" / "review" / "proxy.mp4"
    target.write_bytes(b"proxy-data")
    plan = create_deletion_plan(case.root, [target], reason="manual cleanup")
    plan_path = case.root / "work" / "delete-plan.json"
    plan.write_json(plan_path)

    results = execute_deletion_plan(case.root, plan_path, actor=case.examiner)

    assert not target.exists()
    assert results[0]["status"] == "deleted"
    tombstone = case.root / "state" / "deletion_tombstones.jsonl"
    lines = tombstone.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert plan.plan_id in lines[0]
    assert plan.targets[0].sha256 in lines[0]


def test_execute_preflight_blocks_tampered_target_before_deletion(tmp_path: Path) -> None:
    case = _case(tmp_path)
    first = case.root / "derived" / "review" / "first.mp4"
    second = case.root / "derived" / "review" / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    plan = create_deletion_plan(case.root, [first, second], reason="manual cleanup")
    plan_path = case.root / "work" / "delete-plan.json"
    plan.write_json(plan_path)
    second.write_bytes(b"tampered")

    with pytest.raises(DeletionPlanError):
        execute_deletion_plan(case.root, plan_path)

    assert first.exists()
    assert second.exists()
    assert not (case.root / "state" / "deletion_tombstones.jsonl").exists()


def test_execute_rejects_plan_that_targets_itself(tmp_path: Path) -> None:
    case = _case(tmp_path)
    target = case.root / "derived" / "review" / "plan.json"
    target.write_text("placeholder", encoding="utf-8")
    plan = create_deletion_plan(case.root, [target], reason="self target")
    plan_path = target
    plan.write_json(plan_path, replace=True)

    with pytest.raises(DeletionPlanError, match="may not delete itself"):
        execute_deletion_plan(case.root, plan_path)


def test_execute_rejects_tombstone_overlap(tmp_path: Path) -> None:
    case = _case(tmp_path)
    target = case.root / "derived" / "review" / "proxy.mp4"
    target.write_bytes(b"proxy")
    plan = create_deletion_plan(case.root, [target], reason="overlap test")
    plan_path = case.root / "work" / "delete-plan.json"
    plan.write_json(plan_path)

    with pytest.raises(DeletionPlanError, match="overlap"):
        execute_deletion_plan(case.root, plan_path, tombstone_path=target)
    assert target.exists()


def test_cli_requires_explicit_execute_flag(tmp_path: Path, capsys) -> None:
    case = _case(tmp_path)
    target = case.root / "derived" / "review" / "proxy.mp4"
    target.write_bytes(b"proxy")
    plan = create_deletion_plan(case.root, [target], reason="explicit flag test")
    plan_path = case.root / "work" / "delete-plan.json"
    plan.write_json(plan_path)

    result = review_cli.main(
        [
            "execute-deletion",
            "--case",
            str(case.root),
            "--plan",
            str(plan_path),
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "--execute" in captured.err
    assert target.exists()
