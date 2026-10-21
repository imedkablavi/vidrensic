from __future__ import annotations

from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
import json

from vidrensic.core.case import Case
from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.review_server import ReviewHTTPServer


def _json_get(url: str) -> dict:
    with urlopen(Request(url, headers={"Origin": url.rsplit("/api", 1)[0]}), timeout=5) as response:
        return json.loads(response.read())


def test_review_server_exposes_provenance_backed_metadata(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-HTTP-META", examiner="examiner")
    artifact = case.root / "derived" / "review" / "candidate.mp4"
    artifact.write_bytes(b"candidate")
    item = case.review.register_item(
        artifact,
        forensic_hashes_stable(artifact).sha256,
        kind="media",
        duration_seconds=8.0,
    )
    source = case.root / "reports" / "native.json"
    source.write_text(
        '{"recording_start_utc":"2026-09-10T10:20:30Z","camera_slot":"04"}\n',
        encoding="utf-8",
    )
    source_sha = forensic_hashes_stable(source).sha256
    case.candidate_metadata.set_claim(
        item.item_id,
        item.artifact_sha256,
        field="recording_start_utc",
        value="2026-09-10T10:20:30Z",
        source_kind="native-metadata",
        source_path=source,
        source_sha256=source_sha,
        evidence_pointer="/recording_start_utc",
        confidence=0.99,
    )
    case.candidate_metadata.set_claim(
        item.item_id,
        item.artifact_sha256,
        field="camera_slot",
        value="04",
        source_kind="native-metadata",
        source_path=source,
        source_sha256=source_sha,
        evidence_pointer="/camera_slot",
        confidence=0.98,
    )

    server = ReviewHTTPServer("127.0.0.1", 0, case, "<html>review</html>")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        items = _json_get(base + "/api/items")
        payload = items["items"][0]
        assert payload["candidate_metadata"]["fields"]["recording_start_utc"]["evidence_backed"] is True
        assert payload["candidate_metadata"]["fields"]["camera_slot"]["value"] == "04"

        item_payload = _json_get(base + f"/api/item/{item.item_id}")
        assert item_payload["artifact_sha256"] == item.artifact_sha256
        assert item_payload["candidate_metadata"]["artifact_sha256"] == item.artifact_sha256

        metadata = _json_get(base + f"/api/metadata/{item.item_id}")
        assert metadata["fields"]["recording_start_utc"]["source_sha256"] == source_sha
        assert metadata["fields"]["camera_slot"]["evidence_pointer"] == "/camera_slot"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
