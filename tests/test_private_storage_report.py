from __future__ import annotations

from pathlib import Path
import json
import os
import stat

from vidrensic.profiler.storage import FilesystemHit, PartitionRecord, StorageReport


def test_storage_report_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    report = StorageReport(
        source=Path("/evidence/private-recorder.raw"),
        size_bytes=8192,
        partition_scheme="GPT",
        sector_size=512,
        partitions=(
            PartitionRecord(
                scheme="GPT",
                index=1,
                start_lba=8,
                end_lba=15,
                sector_size=512,
                type_id="synthetic-type",
                unique_id="synthetic-private-id",
                name="recorder-meta",
            ),
        ),
        filesystems=(
            FilesystemHit(
                offset=4096,
                family="EXT2/3/4 family",
                confidence=0.98,
                evidence=("synthetic",),
                partition_index=1,
            ),
        ),
        notes=("synthetic test report",),
    )
    output = tmp_path / "storage.json"

    old_umask = os.umask(0)
    try:
        written = report.write_json(output)
    finally:
        os.umask(old_umask)

    assert written == output.resolve()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["source"] == "/evidence/private-recorder.raw"
    assert data["partitions"][0]["unique_id"] == "synthetic-private-id"
    assert not output.with_name(output.name + ".partial").exists()
