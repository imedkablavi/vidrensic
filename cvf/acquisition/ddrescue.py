from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AcquisitionPlan:
    source: Path
    image: Path
    mapfile: Path
    input_offset: int | None = None
    size_bytes: int | None = None

    def command(self) -> list[str]:
        cmd = ["ddrescue", "-f", "-n"]
        if self.input_offset is not None:
            cmd += ["-i", str(self.input_offset), "-o", "0"]
        if self.size_bytes is not None:
            cmd += ["-s", str(self.size_bytes)]
        cmd += [str(self.source), str(self.image), str(self.mapfile)]
        return cmd
