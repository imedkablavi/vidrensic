from __future__ import annotations

from pathlib import Path

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
