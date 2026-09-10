from __future__ import annotations

from vidrensic import product_cli


def test_product_help_is_clean(capsys) -> None:
    assert product_cli.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "Start here" in output
    assert "vidrensic analyze" in output
    assert "vidrensic-media" in output
    assert "vidrensic-scenes" in output
    assert "vidrensic-duplicates" in output
    assert "vidrensic-repair" in output
    assert "vidrensic-proxy" in output
    assert "vidrensic-review" in output
    assert "vidrensic-review-ui" in output
    assert "vidrensic-export" in output
    assert "vidrensic-profiler" in output
    assert "WFS" not in output
    assert "status=" not in output


def test_advanced_help_is_explicit(capsys) -> None:
    assert product_cli.main(["--advanced-help"]) == 0
    output = capsys.readouterr().out
    assert "Advanced commands" in output
    assert "recover wfs" in output
    assert "vidrensic-scenes" in output
    assert "vidrensic-duplicates" in output
    assert "vidrensic-repair" in output
    assert "vidrensic-proxy" in output
    assert "vidrensic-review" in output
    assert "review timeline" in output.lower()
    assert "review-ui" in output
    assert "vidrensic-profiler" in output
