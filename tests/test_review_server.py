from __future__ import annotations

from http.client import HTTPConnection
from hashlib import sha256
from pathlib import Path
import json
import threading
import time

from vidrensic.core.case import Case
from vidrensic.review_server import ReviewHTTPServer
from vidrensic.review_ui import REVIEW_WORKSTATION_HTML



def _start(case: Case):
    server = ReviewHTTPServer("127.0.0.1", 0, case, REVIEW_WORKSTATION_HTML)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        if server.server_port:
            return server, thread
        time.sleep(0.01)
    server.shutdown()
    thread.join(timeout=1)
    raise RuntimeError("server did not start")


def _request(server: ReviewHTTPServer, method: str, path: str, body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = headers or {}
    if payload is not None:
        request_headers = {**request_headers, "Content-Type": "application/json"}
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, response.getheaders(), data


def test_review_server_serves_ui_items_and_mutations(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "server-case", examiner="examiner")
    artifact = case.root / "derived" / "review" / "clip.mp4"
    artifact.write_bytes(b"0123456789")
    digest = sha256(artifact.read_bytes()).hexdigest()
    item = case.review.register_item(artifact, digest, duration_seconds=20)
    server, thread = _start(case)
    try:
        status, headers, body = _request(server, "GET", "/")
        assert status == 200
        assert "Vidrensic Review Workstation" in body.decode("utf-8")
        assert dict(headers)["Content-Security-Policy"]

        status, _, body = _request(server, "GET", "/api/items")
        assert status == 200
        payload = json.loads(body)
        assert payload["items"][0]["item_id"] == item.item_id

        status, headers, body = _request(
            server,
            "GET",
            f"/media/{item.item_id}",
            headers={"Range": "bytes=2-5"},
        )
        assert status == 206
        assert dict(headers)["Content-Range"] == "bytes 2-5/10"
        assert body == b"2345"

        status, _, body = _request(
            server,
            "POST",
            f"/api/item/{item.item_id}/state",
            {"state": "KEEP", "sha256": digest},
        )
        assert status == 200
        assert json.loads(body)["state"] == "KEEP"

        status, _, body = _request(
            server,
            "POST",
            f"/api/item/{item.item_id}/note",
            {"note": "Primary event", "sha256": digest},
        )
        assert status == 200
        assert json.loads(body)["note"] == "Primary event"

        status, _, body = _request(
            server,
            "POST",
            f"/api/item/{item.item_id}/bookmark",
            {"timestamp_seconds": 4.5, "label": "entry", "note": "event", "sha256": digest},
        )
        assert status == 200
        assert json.loads(body)["label"] == "entry"

        status, _, body = _request(server, "GET", f"/api/item/{item.item_id}")
        assert status == 200
        detail = json.loads(body)
        assert detail["state"] == "KEEP"
        assert detail["note"] == "Primary event"
        assert len(detail["bookmarks"]) == 1
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_review_server_rejects_non_loopback_when_requested_without_flag(tmp_path: Path) -> None:
    from vidrensic.review_server import serve_review_workstation
    case = Case.create(tmp_path, "network-case")
    try:
        serve_review_workstation(case, host="0.0.0.0", port=1, ui_html=REVIEW_WORKSTATION_HTML)
    except ValueError as exc:
        assert "--allow-network" in str(exc)
    else:
        raise AssertionError("non-loopback server was not rejected")
