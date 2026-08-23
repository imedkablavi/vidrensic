from __future__ import annotations

from pathlib import Path
import json

import pytest

import vidrensic.profiles.registry as registry_module
from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json
from vidrensic.profiles.registry import ProfileRegistry


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_bounded_json_accepts_normal_file_and_rejects_size_depth_and_non_file(
    tmp_path: Path,
) -> None:
    normal = _write(tmp_path / "normal.json", {"a": [1, 2, {"b": "ok"}]})
    assert load_bounded_json(normal, max_bytes=1024, max_depth=8)["a"][2]["b"] == "ok"

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b'"' + b"A" * 64 + b'"')
    with pytest.raises(BoundedJSONError, match="maximum size"):
        load_bounded_json(oversized, max_bytes=32)

    deep = _write(tmp_path / "deep.json", {"a": {"b": {"c": {"d": 1}}}})
    with pytest.raises(BoundedJSONError, match="maximum depth"):
        load_bounded_json(deep, max_bytes=1024, max_depth=2)

    with pytest.raises(BoundedJSONError, match="regular file"):
        load_bounded_json(tmp_path, max_bytes=1024)


def test_profile_pack_loads_normal_bounded_schema(tmp_path: Path) -> None:
    pack = _write(
        tmp_path / "pack.json",
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "lab-profile",
                    "family_id": "wfs",
                    "variant": "Lab profile",
                    "vendor_patterns": ["vendor-*"],
                    "model_patterns": [],
                    "firmware_patterns": ["1.*"],
                    "parameters": {"fragment_size": 4096},
                    "notes": ["synthetic test"],
                    "validation_state": "experimental",
                }
            ],
        },
    )
    loaded = ProfileRegistry().load_pack(pack)
    assert len(loaded) == 1
    assert loaded[0].profile_id == "lab-profile"
    assert loaded[0].vendor_patterns == ("vendor-*",)


def test_profile_pack_rejects_oversized_file_before_json_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_module, "MAX_PROFILE_PACK_BYTES", 64)
    pack = tmp_path / "pack.json"
    pack.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {"profile_id": "x", "family_id": "wfs", "notes": ["A" * 128]}
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="maximum size"):
        ProfileRegistry().load_pack(pack)


def test_profile_pack_rejects_profile_and_list_fanout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_module, "MAX_PROFILES_PER_PACK", 1)
    pack = _write(
        tmp_path / "too-many.json",
        {
            "schema_version": 1,
            "profiles": [
                {"profile_id": "one", "family_id": "wfs"},
                {"profile_id": "two", "family_id": "wfs"},
            ],
        },
    )
    with pytest.raises(ValueError, match="exceeds 1 profiles"):
        ProfileRegistry().load_pack(pack)

    monkeypatch.setattr(registry_module, "MAX_PROFILES_PER_PACK", 1024)
    monkeypatch.setattr(registry_module, "MAX_PROFILE_LIST_ITEMS", 1)
    list_pack = _write(
        tmp_path / "too-many-patterns.json",
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "one",
                    "family_id": "wfs",
                    "vendor_patterns": ["a", "b"],
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="vendor_patterns exceeds 1 entries"):
        ProfileRegistry().load_pack(list_pack)


def test_profile_pack_rejects_type_confusion_in_string_lists(tmp_path: Path) -> None:
    pack = _write(
        tmp_path / "bad-list.json",
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "one",
                    "family_id": "wfs",
                    "vendor_patterns": {"not": "a list"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="vendor_patterns must be a list"):
        ProfileRegistry().load_pack(pack)
