from __future__ import annotations

from pathlib import Path
import json

from vidrensic.cli import main


def test_plugins_list(capsys) -> None:
    assert main(["plugins", "list"]) == 0
    output = capsys.readouterr().out
    assert "wfs" in output.lower()


def test_source_inspect_regular_file(tmp_path: Path, capsys) -> None:
    source = tmp_path / "evidence.raw"
    source.write_bytes(b"12345")
    assert main(["source", "inspect", str(source)]) == 0
    output = capsys.readouterr().out
    assert "size_bytes=5" in output
    assert "is_block_device=False" in output


def test_acquire_plan_cli(tmp_path: Path, capsys) -> None:
    source = tmp_path / "evidence.raw"
    source.write_bytes(b"x")
    result = main(
        [
            "acquire",
            "plan",
            str(source),
            "--output",
            str(tmp_path / "out.raw"),
            "--map",
            str(tmp_path / "out.map"),
            "--offset",
            "0x1000",
            "--size",
            "8192",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "ddrescue" in output
    assert "4096" in output
    assert "8192" in output


def test_profile_source_cli(tmp_path: Path, capsys) -> None:
    source = tmp_path / "dvr.img"
    source.write_bytes(b"WFS 0.5" + bytes(1024 * 1024))
    report = tmp_path / "profile.json"
    result = main(
        [
            "profile",
            "source",
            str(source),
            "--sample-size",
            "65536",
            "--sample-count",
            "3",
            "--out",
            str(report),
        ]
    )
    assert result == 0
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["sampling_only"] is True
    assert data["aggregate_signatures"]["wfs_0_5_ascii"] >= 1
    assert str(report.resolve()) in capsys.readouterr().out
