from pathlib import Path

from vidrensic.core.case import Case
from vidrensic.core.review import ReviewState
from vidrensic.review_cli import main


SHA256 = "a" * 64


def test_review_cli_list_and_mutations(tmp_path: Path, capsys) -> None:
    case = Case.create(tmp_path, "cli-review", examiner="examiner")
    artifact = case.root / "derived" / "review" / "clip.mp4"
    artifact.write_bytes(b"video")
    item = case.review.register_item(artifact, SHA256, duration_seconds=20)

    assert main(["list", "--case", str(case.root), "--json"]) == 0
    listed = capsys.readouterr().out
    assert item.item_id in listed
    assert "REVIEW" in listed

    assert main(
        [
            "set-state",
            "--case",
            str(case.root),
            "--item",
            item.item_id,
            "--sha256",
            SHA256,
            "--state",
            "KEEP",
        ]
    ) == 0
    assert "State updated: KEEP" in capsys.readouterr().out

    assert main(
        [
            "note",
            "--case",
            str(case.root),
            "--item",
            item.item_id,
            "--sha256",
            SHA256,
            "--text",
            "Primary event",
        ]
    ) == 0
    assert "Note updated" in capsys.readouterr().out

    assert main(
        [
            "bookmark",
            "--case",
            str(case.root),
            "--item",
            item.item_id,
            "--sha256",
            SHA256,
            "--time",
            "4.25",
            "--label",
            "entry",
        ]
    ) == 0
    assert "Bookmark created" in capsys.readouterr().out

    stored = case.review.get_item(item.item_id)
    assert stored.state is ReviewState.KEEP
    assert stored.note == "Primary event"
    assert case.review.list_bookmarks(item.item_id)[0].label == "entry"
