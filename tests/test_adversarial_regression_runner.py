from __future__ import annotations

from pathlib import Path
import json
import runpy

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_adversarial_regression.py"
MODULE = runpy.run_path(str(SCRIPT))
run_regression = MODULE["run_regression"]
write_json = MODULE["_write_json"]


def test_adversarial_regression_is_deterministic_and_bounded(tmp_path: Path) -> None:
    first = run_regression(
        iterations_per_seed=20,
        seed_count=2,
        max_size=512,
        base_seed=0x1234,
    )
    second = run_regression(
        iterations_per_seed=20,
        seed_count=2,
        max_size=512,
        base_seed=0x1234,
    )

    assert first["seeds"] == [0x1234, 0x1235]
    assert first["total_cases"] == 40
    assert first["counters"] == second["counters"]
    assert "not coverage-guided fuzzing" in first["claim_limit"]

    output = tmp_path / "adversarial.json"
    write_json(output, first)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert loaded["total_cases"] == 40
    assert not output.with_name(output.name + ".tmp").exists()


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"iterations_per_seed": 0, "seed_count": 1, "max_size": 1}, "iterations_per_seed"),
        ({"iterations_per_seed": 1, "seed_count": 0, "max_size": 1}, "seed_count"),
        ({"iterations_per_seed": 1, "seed_count": 1, "max_size": -1}, "max_size"),
        ({"iterations_per_seed": 1, "seed_count": 1, "max_size": 65537}, "max_size"),
    ],
)
def test_adversarial_regression_rejects_unsafe_bounds(kwargs, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        run_regression(**kwargs)
