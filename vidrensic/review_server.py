from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
from typing import Any
from urllib.parse import parse_qs, urlparse

from vidrensic.core.case import Case
from vidrensic.core.candidate_metadata import CandidateMetadataError
from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.review import ReviewState
from vidrensic.media.review_timeline import ReviewTimelineError, build_review_timeline


MAX_BODY_BYTES = 256 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_DISCOVERY_FILES = 512
MAX_DISCOVERY_BYTES = 128 * 1024 * 1024
MAX_RANGE_BYTES = 64 * 1024 * 1024
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,80}$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class ReviewServerError(RuntimeError):
    pass


_INDEX_CACHE: dict[str, dict[str, Path]] = {}
_FINGERPRINT_CACHE: dict[str, tuple[tuple[int, int, int, int], str]] = {}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_item_id(item_id: str) -> str:
    if not ITEM_ID_RE.fullmatch(item_id):
        raise ReviewServerError("invalid review item identifier")
    return item_id


def _artifact_hash(case: Case, item_id: str, path: Path, expected_sha256: str) -> str:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ReviewServerError("review artifact became a symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not _is_inside(case.root, resolved):
        raise ReviewServerError("review artifact is no longer a regular file inside the case")
    stat = resolved.stat()
    fingerprint = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    key = str(resolved)
    cached = _FINGERPRINT_CACHE.get(key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    digest = forensic_hashes_stable(resolved).sha256
    _FINGERPRINT_CACHE[key] = (fingerprint, digest)
    if digest != expected_sha256:
        raise ReviewServerError(
            "review artifact changed after registration; current SHA-256 does not match the review item"
        )
    return digest


def _read_json_file(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > max_bytes:
        return None
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _discover_reports(case: Case, item_sha256: str) -> tuple[Path | None, Path | None, Path | None]:
    cache_key = f"{case.root}:{item_sha256}"
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached.get("contract"), cached.get("timeline"), cached.get("decoder")

    contract: Path | None = None
    timeline: Path | None = None
    decoder: Path | None = None
    reports_root = case.root / "reports"
    seen_files = 0
    seen_bytes = 0
    try:
        paths = sorted(reports_root.rglob("*.json"), key=lambda value: str(value))
    except OSError:
        paths = []

    for path in paths:
        if seen_files >= MAX_DISCOVERY_FILES or seen_bytes >= MAX_DISCOVERY_BYTES:
            break
        if path.is_symlink():
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(case.root)
            size = resolved.stat().st_size
        except (OSError, ValueError):
            continue
        if not resolved.is_file() or size > 8 * 1024 * 1024:
            continue
        seen_files += 1
        seen_bytes += size
        data = _read_json_file(resolved)
        if not data:
            continue
        if data.get("contract", {}).get("kind") == "review-timeline":
            bindings = data.get("bindings", {})
            if bindings.get("review_item_sha256", "").lower() == item_sha256:
                contract = resolved
                continue
        hashes = data.get("hashes")
        if not isinstance(hashes, dict) or hashes.get("sha256", "").lower() != item_sha256:
            continue
        if isinstance(data.get("timeline"), dict):
            timeline = resolved
        if isinstance(data.get("decoder_errors"), dict):
            decoder = resolved

    result = {"contract": contract, "timeline": timeline, "decoder": decoder}
    _INDEX_CACHE[cache_key] = result
    return contract, timeline, decoder


def _candidate_metadata(case: Case, item_id: str, artifact_sha256: str) -> dict[str, Any]:
    try:
        metadata = case.candidate_metadata.get(item_id, artifact_sha256)
    except CandidateMetadataError as exc:
        raise ReviewServerError(str(exc)) from exc
    return metadata.to_dict()


def _items_payload(case: Case, state: ReviewState | None) -> list[dict[str, Any]]:
    items = case.review.list_items(state=state, limit=1000)
    payload: list[dict[str, Any]] = []
    for item in items:
        changed = False
        try:
            _artifact_hash(case, item.item_id, item.artifact, item.artifact_sha256)
        except ReviewServerError:
            changed = True
        contract, timeline, decoder = _discover_reports(case, item.artifact_sha256)
        bookmarks = case.review.list_bookmarks(item.item_id, limit=1000)
        metadata = _candidate_metadata(case, item.item_id, item.artifact_sha256)
        payload.append(
            {
                **item.to_dict(),
                "artifact_changed": changed,
                "timeline_available": contract is not None or timeline is not None,
                "decoder_available": decoder is not None,
                "bookmark_count": len(bookmarks),
                "candidate_metadata": metadata,
            }
        )
    return payload


class _ReviewHandler(BaseHTTPRequestHandler):
    server_version = "VidrensicReview/1"

    @property
    def review_server(self) -> "ReviewHTTPServer":
        return self.server  # type: ignore[return-value]

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/json; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
        )
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, value: Any) -> None:
        self._send(status, _json_bytes(value))

    def _read_body(self) -> dict[str, Any]:
        length = self.headers.get("Content-Length")
        if length is None:
            raise ReviewServerError("request body length is required")
        try:
            size = int(length)
        except ValueError as exc:
            raise ReviewServerError("invalid request body length") from exc
        if size < 0 or size > MAX_BODY_BYTES:
            raise ReviewServerError("request body exceeds safety limit")
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise ReviewServerError("incomplete request body")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise ReviewServerError("request body is not valid JSON") from exc
        if not isinstance(value, dict):
            raise ReviewServerError("request body must be a JSON object")
        return value

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        expected = f"http://{self.review_server.host}:{self.review_server.server_port}"
        return origin == expected

    def do_GET(self) -> None:
        try:
            if not self._origin_ok():
                self._json(403, {"error": "origin rejected"})
                return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, self.review_server.ui_html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/items":
                query = parse_qs(parsed.query)
                raw_state = query.get("state", [None])[0]
                state = ReviewState(raw_state) if raw_state else None
                self._json(200, {"items": _items_payload(self.review_server.case, state)})
                return
            match = re.fullmatch(r"/api/item/([A-Za-z0-9-]{1,80})", parsed.path)
            if match:
                self._api_item(match.group(1))
                return
            match = re.fullmatch(r"/api/metadata/([A-Za-z0-9-]{1,80})", parsed.path)
            if match:
                self._api_metadata(match.group(1))
                return
            match = re.fullmatch(r"/api/timeline/([A-Za-z0-9-]{1,80})", parsed.path)
            if match:
                self._api_timeline(match.group(1))
                return
            match = re.fullmatch(r"/media/([A-Za-z0-9-]{1,80})", parsed.path)
            if match:
                self._media(match.group(1))
                return
            self._json(404, {"error": "not found"})
        except (
            KeyError,
            ValueError,
            ReviewServerError,
            OSError,
            CandidateMetadataError,
            ReviewTimelineError,
        ) as exc:
            self._json(400, {"error": str(exc)})

    def do_POST(self) -> None:
        try:
            if not self._origin_ok():
                self._json(403, {"error": "origin rejected"})
                return
            parsed = urlparse(self.path)
            body = self._read_body()
            match = re.fullmatch(r"/api/item/([A-Za-z0-9-]{1,80})/state", parsed.path)
            if match:
                self._mutate_state(match.group(1), body)
                return
            match = re.fullmatch(r"/api/item/([A-Za-z0-9-]{1,80})/note", parsed.path)
            if match:
                self._mutate_note(match.group(1), body)
                return
            match = re.fullmatch(r"/api/item/([A-Za-z0-9-]{1,80})/bookmark", parsed.path)
            if match:
                self._mutate_bookmark(match.group(1), body)
                return
            self._json(404, {"error": "not found"})
        except (KeyError, ValueError, ReviewServerError, OSError) as exc:
            self._json(400, {"error": str(exc)})

    def _api_item(self, item_id: str) -> None:
        item_id = _safe_item_id(item_id)
        item = self.review_server.case.review.get_item(item_id)
        changed = False
        try:
            _artifact_hash(self.review_server.case, item_id, item.artifact, item.artifact_sha256)
        except ReviewServerError:
            changed = True
        self._json(
            200,
            {
                **item.to_dict(),
                "artifact_changed": changed,
                "bookmarks": [bookmark.to_dict() for bookmark in self.review_server.case.review.list_bookmarks(item_id)],
                "candidate_metadata": _candidate_metadata(
                    self.review_server.case,
                    item_id,
                    item.artifact_sha256,
                ),
            },
        )

    def _api_metadata(self, item_id: str) -> None:
        item_id = _safe_item_id(item_id)
        item = self.review_server.case.review.get_item(item_id)
        self._json(
            200,
            _candidate_metadata(self.review_server.case, item_id, item.artifact_sha256),
        )

    def _api_timeline(self, item_id: str) -> None:
        item_id = _safe_item_id(item_id)
        case = self.review_server.case
        item = case.review.get_item(item_id)
        contract_path, timeline_path, decoder_path = _discover_reports(case, item.artifact_sha256)
        if contract_path is not None:
            payload = _read_json_file(contract_path, max_bytes=MAX_JSON_BYTES)
            if payload is None:
                raise ReviewTimelineError("stored review timeline contract could not be read")
            self._json(200, payload)
            return
        if timeline_path is None:
            self._json(404, {"available": False, "error": "no timeline report is available for this artifact"})
            return
        contract = build_review_timeline(case, item_id, timeline_path, decoder_report_path=decoder_path)
        self._json(200, contract.to_dict())

    def _mutate_state(self, item_id: str, body: dict[str, Any]) -> None:
        state = ReviewState(str(body.get("state", "")).upper())
        sha256 = str(body.get("sha256", "")).lower()
        item = self.review_server.case.review.set_state(item_id, state=state, expected_sha256=sha256)
        self._json(200, item.to_dict())

    def _mutate_note(self, item_id: str, body: dict[str, Any]) -> None:
        sha256 = str(body.get("sha256", "")).lower()
        note = body.get("note", "")
        if not isinstance(note, str):
            raise ReviewServerError("note must be a string")
        item = self.review_server.case.review.set_note(item_id, note=note, expected_sha256=sha256)
        self._json(200, item.to_dict())

    def _mutate_bookmark(self, item_id: str, body: dict[str, Any]) -> None:
        sha256 = str(body.get("sha256", "")).lower()
        try:
            timestamp = float(body.get("timestamp_seconds"))
        except (TypeError, ValueError) as exc:
            raise ReviewServerError("timestamp_seconds must be numeric") from exc
        label = body.get("label", "")
        note = body.get("note", "")
        if not isinstance(label, str) or not isinstance(note, str):
            raise ReviewServerError("bookmark label/note must be strings")
        bookmark = self.review_server.case.review.add_bookmark(
            item_id,
            timestamp_seconds=timestamp,
            expected_sha256=sha256,
            label=label,
            note=note,
        )
        self._json(200, bookmark.to_dict())

    def _media(self, item_id: str) -> None:
        item_id = _safe_item_id(item_id)
        case = self.review_server.case
        item = case.review.get_item(item_id)
        artifact = item.artifact.expanduser()
        _artifact_hash(case, item_id, artifact, item.artifact_sha256)
        artifact = artifact.resolve(strict=True)
        size = artifact.stat().st_size
        range_header = self.headers.get("Range")
        start = 0
        end = size - 1
        status = 200
        headers: dict[str, str] = {"Accept-Ranges": "bytes"}
        if range_header:
            if not range_header.startswith("bytes="):
                self._json(416, {"error": "unsupported range unit"})
                return
            spec = range_header[6:].split(",", 1)[0].strip()
            if "-" not in spec:
                self._json(416, {"error": "invalid range"})
                return
            left, right = spec.split("-", 1)
            try:
                if left == "":
                    suffix = int(right)
                    if suffix <= 0:
                        raise ValueError
                    start = max(0, size - suffix)
                else:
                    start = int(left)
                    end = int(right) if right else size - 1
                    if start < 0 or start >= size or end < start:
                        raise ValueError
                    end = min(end, size - 1)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            if end - start + 1 > MAX_RANGE_BYTES:
                end = start + MAX_RANGE_BYTES - 1
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        content_length = end - start + 1
        mime = (
            "video/mp4"
            if artifact.suffix.lower() == ".mp4"
            else "video/x-matroska"
            if artifact.suffix.lower() == ".mkv"
            else "application/octet-stream"
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        with artifact.open("rb", buffering=0) as handle:
            handle.seek(start)
            remaining = content_length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def log_message(self, format: str, *args: Any) -> None:
        return


class ReviewHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, host: str, port: int, case: Case, ui_html: str):
        self.host = host
        self.case = case
        self.ui_html = ui_html
        super().__init__((host, port), _ReviewHandler)


def serve_review_workstation(case: Case, *, host: str, port: int, ui_html: str, allow_network: bool = False) -> None:
    normalized_host = host.strip()
    if normalized_host not in LOOPBACK_HOSTS and not allow_network:
        raise ValueError("non-loopback review server requires --allow-network")
    server = ReviewHTTPServer(normalized_host, port, case, ui_html)
    try:
        server.serve_forever()
    finally:
        server.server_close()
