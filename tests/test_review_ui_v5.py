from vidrensic.review_ui_v5 import REVIEW_WORKSTATION_HTML


def test_v5_ui_contains_provenance_filters_and_safe_projection() -> None:
    html = REVIEW_WORKSTATION_HTML
    for marker in (
        'id="record-date"',
        'id="record-hour"',
        'id="camera"',
        "normalizeMetadata",
        "ambiguous",
        "evidence_backed",
        "PROOF",
        "OBS",
    ):
        assert marker in html


def test_v5_ui_keeps_forensic_boundaries_visible() -> None:
    html = REVIEW_WORKSTATION_HTML
    assert "Recording wall-clock time is not inferred" not in html
    assert "Operator observations remain visible but do not qualify for these filters." in html
    assert "candidate slots" in html
    assert "visual triage aid" in html
