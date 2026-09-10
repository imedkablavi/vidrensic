from __future__ import annotations

from vidrensic.review_ui_v3 import REVIEW_WORKSTATION_HTML as _BASE_HTML


_REPLACEMENTS = (
    (
        "const proven=md.evidence_backed===true;",
        "const recordProof=md.fields?.recording_start_utc?.evidence_backed===true&&!md.fields?.recording_start_utc?.ambiguous;const cameraProof=md.fields?.camera_slot?.evidence_backed===true&&!md.fields?.camera_slot?.ambiguous;",
    ),
    (
        "if($('record-date').value&&(!proven||!start.startsWith($('record-date').value)))return false;if($('record-hour').value&&(!proven||!start.includes(`T${$('record-hour').value}:`)))return false;if($('camera').value.trim()&&(!proven||slot!==$('camera').value.trim()))return false;",
        "if($('record-date').value&&(!recordProof||!start.startsWith($('record-date').value)))return false;if($('record-hour').value&&(!recordProof||!start.includes(`T${$('record-hour').value}:`)))return false;if($('camera').value.trim()&&(!cameraProof||slot!==$('camera').value.trim()))return false;",
    ),
    (
        "const proven=md.evidence_backed===true;return `<div class=\"itemrow\">",
        "const recordProof=md.fields?.recording_start_utc?.evidence_backed===true&&!md.fields?.recording_start_utc?.ambiguous;const cameraProof=md.fields?.camera_slot?.evidence_backed===true&&!md.fields?.camera_slot?.ambiguous;const proven=recordProof||cameraProof;return `<div class=\"itemrow\">",
    ),
)

REVIEW_WORKSTATION_HTML = _BASE_HTML
for _old, _new in _REPLACEMENTS:
    REVIEW_WORKSTATION_HTML = REVIEW_WORKSTATION_HTML.replace(_old, _new)

if REVIEW_WORKSTATION_HTML == _BASE_HTML:
    raise RuntimeError("review workstation v4 patch did not apply")
