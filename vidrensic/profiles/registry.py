from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
import json


PROFILE_SCHEMA_VERSION = 1


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _matches(value: str | None, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    candidate = _norm(value)
    if not candidate:
        return False
    return any(fnmatchcase(candidate, pattern.casefold()) for pattern in patterns)


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
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
        if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"unsupported profile-pack schema: {data.get('schema_version')!r}")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("profile pack must contain a profiles list")
        loaded: list[VariantProfile] = []
        for item in raw_profiles:
            if not isinstance(item, dict):
                raise ValueError("each profile must be an object")
            profile = VariantProfile(
                profile_id=str(item["profile_id"]),
                family_id=str(item["family_id"]),
                variant=str(item.get("variant") or item["profile_id"]),
                vendor_patterns=tuple(str(x) for x in item.get("vendor_patterns", [])),
                model_patterns=tuple(str(x) for x in item.get("model_patterns", [])),
                firmware_patterns=tuple(str(x) for x in item.get("firmware_patterns", [])),
                parameters=dict(item.get("parameters", {})),
                notes=tuple(str(x) for x in item.get("notes", [])),
                validation_state=str(item.get("validation_state", "experimental")),
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
            vendor_patterns=("*dahua*", "*oem*"),
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
                "Compatible with the widely documented DHAV frame layer; vendor/firmware extensions can vary.",
            ),
            validation_state="implementation-tested",
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
