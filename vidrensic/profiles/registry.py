from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json


PROFILE_SCHEMA_VERSION = 1
MAX_PROFILE_PACK_BYTES = 4 * 1024 * 1024
MAX_PROFILES_PER_PACK = 1024
MAX_PROFILE_LIST_ITEMS = 128
MAX_PROFILE_TEXT_CHARS = 4096


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _matches(value: str | None, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    candidate = _norm(value)
    if not candidate:
        return False
    return any(fnmatchcase(candidate, pattern.casefold()) for pattern in patterns)


def _profile_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    if len(value) > MAX_PROFILE_TEXT_CHARS:
        raise ValueError(f"{field_name} exceeds {MAX_PROFILE_TEXT_CHARS} characters")
    return value


def _profile_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    if len(value) > MAX_PROFILE_LIST_ITEMS:
        raise ValueError(f"{field_name} exceeds {MAX_PROFILE_LIST_ITEMS} entries")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only strings")
        if len(item) > MAX_PROFILE_TEXT_CHARS:
            raise ValueError(
                f"{field_name} entry exceeds {MAX_PROFILE_TEXT_CHARS} characters"
            )
        result.append(item)
    return tuple(result)


@dataclass(frozen=True)
class VariantProfile:
    profile_id: str
    family_id: str
    variant: str
    vendor_patterns: tuple[str, ...] = ()
    model_patterns: tuple[str, ...] = ()
    firmware_patterns: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    validation_state: str = "experimental"

    def match_score(
        self,
        *,
        vendor: str | None = None,
        model: str | None = None,
        firmware: str | None = None,
    ) -> float:
        """Score only explicit identifying evidence; generic profiles score low."""

        score = 0.05
        checks = (
            (vendor, self.vendor_patterns, 0.35),
            (model, self.model_patterns, 0.40),
            (firmware, self.firmware_patterns, 0.20),
        )
        for value, patterns, weight in checks:
            if not patterns:
                continue
            if not _matches(value, patterns):
                return 0.0
            score += weight
        return min(score, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "family_id": self.family_id,
            "variant": self.variant,
            "vendor_patterns": list(self.vendor_patterns),
            "model_patterns": list(self.model_patterns),
            "firmware_patterns": list(self.firmware_patterns),
            "parameters": self.parameters,
            "notes": list(self.notes),
            "validation_state": self.validation_state,
        }


class ProfileRegistry:
    def __init__(self, profiles: tuple[VariantProfile, ...] = ()):
        self._profiles: dict[str, VariantProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: VariantProfile) -> None:
        key = profile.profile_id.strip().lower()
        if not key:
            raise ValueError("profile_id cannot be empty")
        if key in self._profiles:
            raise ValueError(f"duplicate profile_id: {profile.profile_id}")
        if not profile.family_id.strip():
            raise ValueError("family_id cannot be empty")
        if not profile.variant.strip():
            raise ValueError("variant cannot be empty")
        if not isinstance(profile.parameters, dict):
            raise ValueError("profile parameters must be an object")
        self._profiles[key] = profile

    def get(self, profile_id: str) -> VariantProfile:
        try:
            return self._profiles[profile_id.lower()]
        except KeyError as exc:
            raise KeyError(f"unknown variant profile: {profile_id}") from exc

    def all(self) -> tuple[VariantProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def match(
        self,
        *,
        vendor: str | None = None,
        model: str | None = None,
        firmware: str | None = None,
        family_id: str | None = None,
    ) -> tuple[tuple[float, VariantProfile], ...]:
        rows = []
        for profile in self._profiles.values():
            if family_id and profile.family_id.casefold() != family_id.casefold():
                continue
            score = profile.match_score(vendor=vendor, model=model, firmware=firmware)
            if score > 0:
                rows.append((score, profile))
        rows.sort(key=lambda item: (-item[0], item[1].profile_id))
        return tuple(rows)

    def load_pack(self, path: Path) -> tuple[VariantProfile, ...]:
        try:
            data = load_bounded_json(
                path,
                max_bytes=MAX_PROFILE_PACK_BYTES,
                max_depth=32,
                max_nodes=100_000,
                max_string_chars=64 * 1024,
                label="profile pack",
            )
        except BoundedJSONError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(data, dict):
            raise ValueError("profile pack must be a JSON object")
        if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"unsupported profile-pack schema: {data.get('schema_version')!r}")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("profile pack must contain a profiles list")
        if len(raw_profiles) > MAX_PROFILES_PER_PACK:
            raise ValueError(f"profile pack exceeds {MAX_PROFILES_PER_PACK} profiles")

        loaded: list[VariantProfile] = []
        for item in raw_profiles:
            if not isinstance(item, dict):
                raise ValueError("each profile must be an object")
            required = ("profile_id", "family_id")
            missing = [name for name in required if name not in item]
            if missing:
                raise ValueError(f"profile missing required fields: {', '.join(missing)}")
            parameters = item.get("parameters", {})
            if not isinstance(parameters, dict):
                raise ValueError("profile parameters must be an object")

            profile_id = _profile_text(item["profile_id"], "profile_id")
            family_id = _profile_text(item["family_id"], "family_id")
            variant = _profile_text(item.get("variant") or profile_id, "variant")
            validation_state = _profile_text(
                item.get("validation_state", "experimental"),
                "validation_state",
            )
            profile = VariantProfile(
                profile_id=profile_id,
                family_id=family_id,
                variant=variant,
                vendor_patterns=_profile_string_list(
                    item.get("vendor_patterns", []), "vendor_patterns"
                ),
                model_patterns=_profile_string_list(
                    item.get("model_patterns", []), "model_patterns"
                ),
                firmware_patterns=_profile_string_list(
                    item.get("firmware_patterns", []), "firmware_patterns"
                ),
                parameters=dict(parameters),
                notes=_profile_string_list(item.get("notes", []), "notes"),
                validation_state=validation_state,
            )
            self.register(profile)
            loaded.append(profile)
        return tuple(loaded)


def builtin_profiles() -> tuple[VariantProfile, ...]:
    return (
        VariantProfile(
            profile_id="wfs-observed-0.5-framing",
            family_id="wfs",
            variant="Observed WFS 0.5 framing",
            parameters={
                "fragment_size": 2 * 1024 * 1024,
                "record_sync_hex": "000001",
                "video_record_types": ["fc", "fd", "fe"],
                "wrapper_record_types": ["f9", "fa"],
                "timestamp_scheme": "packed-year-month-day-hour-minute-second-2000",
            },
            notes=(
                "Derived from the project's validated recovery corpus; not a universal WFS definition.",
            ),
            validation_state="case-validated",
        ),
        VariantProfile(
            profile_id="dhav-classic-24-8",
            family_id="dhav",
            variant="Classic DHAV 24-byte header / 8-byte footer",
            parameters={
                "header_magic": "DHAV",
                "header_size": 24,
                "footer_magic": "dhav",
                "footer_size": 8,
                "frame_length_offset": 12,
                "channel_offset": 6,
                "timestamp_offset": 16,
            },
            notes=(
                "Structural profile is vendor-neutral; Dahua-family and OEM systems are common sources, but the bytes decide compatibility.",
                "Firmware extensions can vary and must be profiled rather than forced into this layout.",
            ),
            validation_state="implementation-tested",
        ),
        VariantProfile(
            profile_id="hikvision-master-256-v1",
            family_id="hikvision",
            variant="Hikvision 256-byte Master Sector candidate layout",
            vendor_patterns=("*hikvision*", "*hik*"),
            parameters={
                "master_signature_ascii": "HIKVISION@HANGZHOU",
                "master_size": 256,
                "hdd_capacity_offset": 56,
                "system_logs_offset_offset": 80,
                "system_logs_size_offset": 88,
                "video_data_offset_offset": 104,
                "data_block_size_offset": 120,
                "total_data_blocks_offset": 128,
                "hikbtree1_offset_offset": 136,
                "hikbtree1_size_offset": 144,
                "hikbtree2_offset_offset": 152,
                "hikbtree2_size_offset": 160,
                "initialization_time_offset": 224,
            },
            notes=(
                "Used only for Master Sector profiling in 0.4-alpha; HIKBTREE/data-block recovery is not yet claimed.",
                "Master Sector location is searched dynamically rather than assumed to be at one fixed disk offset.",
            ),
            validation_state="profile-only",
        ),
        VariantProfile(
            profile_id="annexb-generic",
            family_id="annexb",
            variant="Generic H.264/H.265 Annex-B",
            parameters={"start_codes": ["000001", "00000001"]},
            validation_state="standard-format",
        ),
        VariantProfile(
            profile_id="mpegps-generic",
            family_id="mpegps",
            variant="Generic MPEG Program Stream/PES",
            parameters={"pack_start_code": "000001ba"},
            validation_state="standard-format",
        ),
    )


def default_profile_registry() -> ProfileRegistry:
    return ProfileRegistry(builtin_profiles())
