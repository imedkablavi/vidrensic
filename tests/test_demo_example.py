from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from vidrensic.cli import default_registry
from vidrensic.plugins.dhav.scanner import scan_dhav_frames


def test_public_demo_generator_stays_detectable_and_recoverable(tmp_path: Path) -> None:
    source = tmp_path / "synthetic-dhav.raw"
    script = Path(__file__).resolve().parents[1] / "examples" / "generate_dhav_demo.py"

    subprocess.run(
        [sys.executable, str(script), "--out", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )

    report = default_registry().detection_report(source)
    assert report.best.plugin == "dhav"
    assert report.best.confidence >= 0.78

    frames = scan_dhav_frames(source)
    assert len(frames) == 12
    assert {frame.header.channel for frame in frames} == {0, 1}
    assert all(frame.structurally_valid for frame in frames)
