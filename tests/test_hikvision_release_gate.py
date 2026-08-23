from __future__ import annotations

import json
from pathlib import Path

from vidrensic.plugins.capabilities import FormatOperation, SupportLevel
from vidrensic.plugins.hikvision.plugin import HikvisionPlugin


def test_hikvision_stays_profile_only_without_admitted_real_fixtures() -> None:
    index = json.loads(
        Path("validation_corpus/real/real-corpus-index.json").read_text(encoding="utf-8")
    )
    real_hikvision = [
        case
        for case in index["cases"]
        if case.get("family") == "hikvision" and case.get("provenance") != "synthetic"
    ]
    assert real_hikvision == []

    descriptor = HikvisionPlugin.descriptor
    assert descriptor.support_level == SupportLevel.PROFILE
    assert descriptor.operations == (FormatOperation.DETECT, FormatOperation.PROFILE)
    assert descriptor.supports(SupportLevel.PARSE) is False
    assert descriptor.supports(SupportLevel.RECONSTRUCT) is False
