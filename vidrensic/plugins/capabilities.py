from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class SupportLevel(IntEnum):
    """Highest validated stage implemented for a format family.

    Values are ordered so callers can safely ask whether a family supports at
    least a given stage. A higher value does not imply independent forensic
    validation; it only describes software capability.
    """

    NONE = 0
    DETECT = 10
    PROFILE = 20
    PARSE = 30
    RECONSTRUCT = 40
    VALIDATE = 50
    EXPORT = 60


class FormatOperation(str, Enum):
    """Concrete operations currently implemented for a format family."""

    DETECT = "detect"
    PROFILE = "profile"
    DATE_SCAN = "date-scan"
    STREAM_PARSE = "stream-parse"
    NATIVE_RECOVER = "native-recover"
    CHANNEL_DEMUX = "channel-demux"
    MEDIA_QC = "media-qc"
    FORENSIC_EXPORT = "forensic-export"


class StorageTopology(str, Enum):
    UNKNOWN = "unknown"
    KNOWN_FILESYSTEM = "known-filesystem"
    PROPRIETARY_FILESYSTEM = "proprietary-filesystem"
    KNOWN_FS_PLUS_PROPRIETARY_DATA = "known-fs-plus-proprietary-data"
    CIRCULAR_BUFFER = "circular-buffer"
    RAW_INTERLEAVED = "raw-interleaved"
    CONTAINER_ONLY = "container-only"
    ELEMENTARY_STREAM = "elementary-stream"


class RecoveryStrategy(str, Enum):
    INDEX_GUIDED = "index-guided"
    TIMESTAMP_GUIDED = "timestamp-guided"
    SIGNATURE_CARVE = "signature-carve"
    FRAGMENT_CHAIN = "fragment-chain"
    GLOBAL_FRAGMENT_GRAPH = "global-fragment-graph"
    CHANNEL_DEMUX = "channel-demux"
    FRAME_LEVEL_SALVAGE = "frame-level-salvage"
    KNOWN_FILESYSTEM_WALK = "known-filesystem-walk"
    STREAM_COPY = "stream-copy"
    CONTROLLED_TRANSCODE = "controlled-transcode"


class FailureMode(str, Enum):
    MISSING_OR_CORRUPT_INDEX = "missing-or-corrupt-index"
    DELETED_RECORDING = "deleted-recording"
    PARTIAL_OVERWRITE = "partial-overwrite"
    CIRCULAR_WRAP = "circular-wrap"
    INTERLEAVED_CAMERAS = "interleaved-cameras"
    CHANNEL_SLOT_DRIFT = "channel-slot-drift"
    FRAGMENTATION = "fragmentation"
    BAD_SECTORS = "bad-sectors"
    TRUNCATED_RECORD = "truncated-record"
    BROKEN_CONTAINER_INDEX = "broken-container-index"
    DAMAGED_GOP = "damaged-gop"
    TIMESTAMP_GAPS = "timestamp-gaps"
    TIMESTAMP_DRIFT = "timestamp-drift"
    VARIABLE_OR_WRONG_FPS = "variable-or-wrong-fps"
    WRONG_PLAYBACK_DURATION = "wrong-playback-duration"
    MIXED_CODEC_OR_VARIANT = "mixed-codec-or-variant"
    AUDIO_VIDEO_DESYNC = "audio-video-desync"
    UNKNOWN_VENDOR_VARIANT = "unknown-vendor-variant"


@dataclass(frozen=True)
class FormatDescriptor:
    """Product-level description of a storage/container family.

    `support_level` summarizes maturity. `operations` is the authoritative set
    of concrete commands the family may currently perform. This distinction
    prevents a PROFILE-only family from silently accepting a recovery command.
    """

    family_id: str
    display_name: str
    support_level: SupportLevel
    topology: StorageTopology
    operations: tuple[FormatOperation, ...] = ()
    aliases: tuple[str, ...] = ()
    vendor_hints: tuple[str, ...] = ()
    codecs: tuple[str, ...] = ()
    timestamp_kinds: tuple[str, ...] = ()
    strategies: tuple[RecoveryStrategy, ...] = ()
    failure_modes: tuple[FailureMode, ...] = ()
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports(self, level: SupportLevel) -> bool:
        return self.support_level >= level

    def supports_operation(self, operation: FormatOperation) -> bool:
        return operation in self.operations

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "display_name": self.display_name,
            "support_level": self.support_level.name,
            "support_level_value": int(self.support_level),
            "topology": self.topology.value,
            "operations": [item.value for item in self.operations],
            "aliases": list(self.aliases),
            "vendor_hints": list(self.vendor_hints),
            "codecs": list(self.codecs),
            "timestamp_kinds": list(self.timestamp_kinds),
            "strategies": [item.value for item in self.strategies],
            "failure_modes": [item.value for item in self.failure_modes],
            "notes": list(self.notes),
            "metadata": self.metadata,
        }
