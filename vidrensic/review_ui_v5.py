from __future__ import annotations

from vidrensic.review_ui_v4 import REVIEW_WORKSTATION_HTML as _BASE_HTML


_OLD = "const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const t=v=>{if(!Number.isFinite(v))return'—';"
_NEW = "const $=id=>document.getElementById(id);const normalizeMetadata=md=>{const claims=Array.isArray(md.claims)?md.claims:[];const fields={};for(const field of ['recording_start_utc','recording_end_utc','camera_slot','source_label','format_family']){const xs=claims.filter(c=>c.field===field);const values=[...new Set(xs.map(c=>c.value))];const proof=xs.some(c=>c.evidence_backed===true)&&values.length===1;fields[field]={value:values.length===1?values[0]:null,ambiguous:values.length>1,evidence_backed:proof,claim_count:xs.length}}return {...md,fields,evidence_backed:Object.values(fields).some(x=>x.evidence_backed)};};const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const t=v=>{if(!Number.isFinite(v))return'—';"

REVIEW_WORKSTATION_HTML = _BASE_HTML.replace(_OLD, _NEW)
REVIEW_WORKSTATION_HTML = REVIEW_WORKSTATION_HTML.replace(
    "const md=i.candidate_metadata||{};",
    "const md=normalizeMetadata(i.candidate_metadata||{});",
)
REVIEW_WORKSTATION_HTML = REVIEW_WORKSTATION_HTML.replace(
    "renderMetadata(d.candidate_metadata||{});",
    "renderMetadata(normalizeMetadata(d.candidate_metadata||{}));",
)

if REVIEW_WORKSTATION_HTML == _BASE_HTML:
    raise RuntimeError("review workstation v5 patch did not apply")
