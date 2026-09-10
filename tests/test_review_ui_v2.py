from vidrensic.review_ui_v2 import REVIEW_WORKSTATION_HTML


def test_expanded_review_ui_contains_workstation_features() -> None:
    html = REVIEW_WORKSTATION_HTML
    for marker in (
        'id="date"',
        'id="hour"',
        'id="matrix-open"',
        'id="contact"',
        'id="retry"',
        'Maximum 4 candidates in synchronized matrix',
        'Playback interruption',
        '0.25×',
        'Frame −',
        'Frame +',
        'KEEP',
        'DISCARD',
    ):
        assert marker in html


def test_ui_does_not_claim_recording_date_when_contract_lacks_it() -> None:
    assert "review-update UTC" in REVIEW_WORKSTATION_HTML
    assert "recorder wall-clock metadata is not currently part of ReviewItem" in REVIEW_WORKSTATION_HTML
