from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic import duplicate_cli


def _report(path: Path):
    exact = SimpleNamespace(classification="EXACT")
    near = SimpleNamespace(classification="NEAR_DUPLICATE_CANDIDATE")
    distinct = SimpleNamespace(classification="DISTINCT")
    review = SimpleNamespace(classification="REVIEW")
    return SimpleNamespace(
        sources=(SimpleNamespace(path=path), SimpleNamespace(path=path)),
        comparisons=(exact, near, distinct, review),
        to_dict=lambda: {
            "schema_version": 1,
            "analysis": {"derived": True},
            "comparisons": [{"classification": "EXACT"}],
        },
        write_json=lambda output: output.write_text('{"schema_version":1}\n', encoding="utf-8"),
    )


def test_duplicate_cli_human_output(monkeypatch, tmp_path: Path, capsys) -> None:
    left = tmp_path / "a.mp4"
    right = tmp_path / "b.mp4"
    report_path = tmp_path / "duplicates.json"
    left.write_bytes(b"a")
    right.write_bytes(b"b")
    monkeypatch.setattr(
        duplicate_cli,
        "analyze_media_set",
        lambda *args, **kwargs: _report(left),
    )

    assert duplicate_cli.main([str(left), str(right), "--out", str(report_path)]) == 0
    output = capsys.readouterr().out
    assert "Duplicate analysis complete" in output
    assert "NEAR_DUPLICATE_CANDIDATE" in output
    assert report_path.exists()


def test_duplicate_cli_json_output(monkeypatch, tmp_path: Path, capsys) -> None:
    left = tmp_path / "a.mp4"
    report_path = tmp_path / "duplicates.json"
    left.write_bytes(b"a")
    monkeypatch.setattr(duplicate_cli, "analyze_media_set", lambda *args, **kwargs: _report(left))

    assert duplicate_cli.main([str(left), str(left), "--out", str(report_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["analysis"]["derived"] is True


def test_duplicate_cli_rejects_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "duplicates.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        duplicate_cli.main(["a.mp4", "b.mp4", "--out", str(output)])
    assert exc.value.code == 2
