from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import vidrensic.cli_ext as cli_ext


def test_product_help_is_user_facing(capsys) -> None:
    assert cli_ext.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "Start here" in output
    assert "analyze <source> --out <report>" in output
    assert "--advanced-help" in output
    assert "WFS" not in output
    assert "status=" not in output


def test_analyze_shows_summary_and_keeps_technical_report_separate(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recorder.img"
    report_path = tmp_path / "analysis.json"
    source.write_bytes(b"fixture")

    fake_report = SimpleNamespace(
        source=source,
        source_info={"size_bytes": 4096},
        storage={"filesystems": [{"type": "ext4"}]},
        format_detection={
            "requires_review": False,
            "results": [{"plugin": "wfs", "confidence": 0.94}],
        },
        recommended_actions=("profile WFS fragment alignment/data-area evidence before recovery",),
    )
    fake_report.to_dict = lambda: {
        "schema_version": 1,
        "source": str(source),
        "format_detection": fake_report.format_detection,
    }
    fake_report.write_json = lambda path: path
    monkeypatch.setattr(cli_ext, "triage_source", lambda *args, **kwargs: fake_report)

    assert cli_ext.main(["analyze", str(source), "--out", str(report_path)]) == 0
    output = capsys.readouterr().out
    assert "Analysis complete" in output
    assert "Detection" in output
    assert "WFS" in output
    assert "High" in output
    assert "Profile the WFS layout" in output
    assert "status=" not in output
    assert "strategy=" not in output


def test_review_state_is_visible_but_concise(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "unknown.img"
    source.write_bytes(b"fixture")

    fake_report = SimpleNamespace(
        source=source,
        source_info={"size_bytes": 1024},
        storage={"filesystems": []},
        format_detection={
            "requires_review": True,
            "results": [
                {"plugin": "wfs", "confidence": 0.68},
                {"plugin": "dhav", "confidence": 0.66},
            ],
        },
        recommended_actions=("do not auto-select a proprietary parser; review ranked family evidence",),
    )
    fake_report.to_dict = lambda: {"format_detection": fake_report.format_detection}
    fake_report.write_json = lambda path: path
    monkeypatch.setattr(cli_ext, "triage_source", lambda *args, **kwargs: fake_report)

    assert cli_ext.main(["analyze", str(source), "--out", str(tmp_path / "report.json")]) == 3
    output = capsys.readouterr().out
    assert "Review required" in output
    assert "No automatic format decision was made" in output
    assert "0.68" not in output
    assert "requires_review=" not in output
