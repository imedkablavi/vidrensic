<div align="center">

# VIDRENSIC

### DVR / NVR Evidence Reconstruction & Video Forensics

**Acquire. Reconstruct. Validate. Review. Export.**

![Stage](https://img.shields.io/badge/stage-alpha-orange)
![Platform](https://img.shields.io/badge/platform-Linux-222222?logo=linux)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-Proprietary-red)
![Evidence](https://img.shields.io/badge/evidence-read--only%20first-0A7B83)

**A forensic-first platform for proprietary surveillance storage.**

</div>

---

## What is Vidrensic?

Vidrensic is a Linux-first forensic platform for recovering and examining video from proprietary DVR/NVR storage systems where ordinary filesystem undelete and generic file carving are not enough.

It is designed around the reality of surveillance evidence: interleaved camera fragments, overwritten metadata, proprietary timestamps, partial recordings, damaged media, unstable camera-slot ordering, unusual codecs, and source disks that should be treated as evidence rather than repaired in place.

The project is intentionally broader than one filesystem. **WFS is the first recovery plugin**, while the core is being built to support additional DVR/NVR formats through isolated plugins.

> **Current status:** `0.2.0-alpha`. The architecture is usable for development and validation, but the project must not yet be represented as independently validated forensic software.

---

## Why this project exists

Traditional recovery tools usually answer: “Can I find a file?”

Vidrensic must answer a harder set of questions:

- Which physical fragments belong to the same recording?
- Which fragments belong to different cameras recorded at the same time?
- Is a one-hour output actually one coherent camera stream?
- Was part of the recording overwritten or merely unindexed?
- Is the timestamp native evidence or a derived estimate?
- Can the recovered stream decode at the beginning, middle, and end?
- What changed between source, reconstructed native stream, and review copy?
- Can another examiner reproduce the result from the same evidence and parameters?

Those questions drive the design.

---

## Forensic pipeline

```text
┌──────────────────────────────┐
│ Evidence Source              │
│ disk • image • clone         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Source Safety & Acquisition  │
│ RO check • SMART • ddrescue  │
│ hashes • range acquisition   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Format Detection / Plugins   │
│ WFS • future DVR/NVR formats │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Recording Reconstruction     │
│ fragments • graph evidence   │
│ timestamps • packet joins    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Native Stream Extraction     │
│ HEVC/H.264 • metadata        │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Validation & QC              │
│ ffprobe • decode • timeline  │
│ corruption • ambiguity       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Review Workstation           │
│ matrix • timeline • KEEP     │
│ notes • bookmarks • preview  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Evidence Export              │
│ native • review • hashes     │
│ manifests • audit • reports  │
└──────────────────────────────┘
```

---

## Current capabilities

| Area | Status | What exists now |
|---|---:|---|
| Case engine | ✅ | Structured case directories and machine-readable case metadata |
| Audit | ✅ | Append-only JSONL events with SHA-256 hash chaining and verification |
| Hashing | ✅ | SHA-256/SHA-512 streaming hashes |
| Linux source inspection | ✅ | File/block-device inspection, source size, RO state and mount reporting |
| Acquisition planning | ✅ | Safe GNU ddrescue command generation, ranges, map files and capacity checks |
| Acquisition execution | 🧪 | Controlled subprocess execution; no shell interpolation |
| Plugin framework | ✅ | Isolated format plugin API and registry |
| WFS timestamps | ✅ | Decode/encode support for observed WFS timestamp words |
| WFS record parser | ✅ | FD/FE/FC/FA/F9 framing with conservative length validation |
| WFS timeline scan | ✅ | Fragment-boundary recording-start discovery by date |
| WFS reconstruction | 🧪 | Conservative multi-stream fragment continuation with mutual exclusion |
| Native HEVC extraction | 🧪 | Packet payload extraction from reconstructed WFS chains |
| Media probing | ✅ | Structured ffprobe integration |
| Review workstation | 🚧 | Next major milestone |
| Court/report package | 🚧 | Planned after case/export schema stabilizes |

Legend: ✅ implemented • 🧪 implemented but still being validated • 🚧 planned/in progress

---

## Safety model

Vidrensic follows several non-negotiable rules:

1. **The evidence source is never repaired or mounted by Vidrensic.**
2. **Block devices are expected to be read-only.** Write-enabled devices are rejected unless an explicit forensic override is used and audited.
3. **Ambiguity is preserved.** A technically playable result is not automatically a forensic PASS.
4. **Native evidence and review proxies remain separate.**
5. **Original timestamps are preserved.** Derived/interpolated time must be labeled as derived.
6. **Destructive actions are opt-in.** Cleanup/export decisions never silently modify source evidence.
7. **Every important operation is intended to be reproducible from logged parameters and hashes.**

---

## CLI preview

```bash
# Create a case
vidrensic case create CASE-2026-001 --root /cases --examiner "Examiner"

# Inspect a source before acquisition
vidrensic source inspect /dev/sdb

# Build a selective ddrescue acquisition plan
vidrensic acquire plan /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/day09.raw \
  --map /cases/CASE-2026-001/acquisitions/day09.map \
  --offset 1122820554752 \
  --size 12582912000

# Run the acquisition after safety checks
vidrensic acquire run /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/day09.raw \
  --map /cases/CASE-2026-001/acquisitions/day09.map \
  --offset 1122820554752 \
  --size 12582912000 \
  --case /cases/CASE-2026-001

# List forensic format plugins
vidrensic plugins list

# Scan WFS recording starts
vidrensic scan /cases/CASE-2026-001/acquisitions/day09.raw \
  --plugin wfs \
  --date 2026-08-09
```

---

## Repository structure

```text
vidrensic/
├── acquisition/       evidence source inspection and ddrescue orchestration
├── core/              cases, models, hashing and audit
├── media/             probing and technical media validation
├── plugins/
│   └── wfs/           WFS parser, scanner and reconstruction engine
└── recovery/          format-neutral graph/reconstruction primitives

docs/                  architecture, forensic policy and roadmap
tests/                 unit + synthetic forensic fixtures
.github/workflows/      CI and regression checks
```

---

## Evidence states

Vidrensic uses explicit states instead of a single “recovered” label:

| State | Meaning |
|---|---|
| `PASS` | Required validation ran and no hard or ambiguous condition remains |
| `REVIEW` | Candidate exists, but evidence is incomplete, ambiguous, or requires examiner review |
| `FAIL` | Structural, decoding, timing, or integrity evidence is strongly inconsistent |
| `UNKNOWN` | Validation required for a decision has not been performed |

A one-hour duration alone is never sufficient for `PASS`.

---

## Product roadmap

The next development tracks are:

- evidence-source profiler for unknown DVR/NVR formats;
- resumable job database and checkpoint engine;
- WFS global weighted graph solver;
- frame-level salvage for partially overwritten recordings;
- keyframe and decoder-error maps;
- synchronized multi-camera review matrix;
- sticky preview with frame stepping, ±5s seeking and high-speed review;
- camera-correlation evidence without assuming stable slot order;
- native vs review-copy export profiles;
- signed manifests and case packages;
- HTML/PDF technical and chain-of-custody reporting;
- plugin SDK and synthetic corruption corpus.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the engineering sequence.

---

## Ownership & licensing

**Project owner / lead developer:** `@imedkablavi`

Copyright © 2026 imedkablavi. All rights reserved.

This repository is **proprietary software**. Repository access does not grant permission to redistribute, sublicense, sell, publish, or incorporate the source into another product. See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md), and [`AUTHORS.md`](AUTHORS.md).

---

## Validation notice

Forensic software requires more than functional code. Before production or evidentiary use, Vidrensic should be validated against documented known-good and deliberately corrupted test media, with repeatable expected results and version-controlled validation records.

<div align="center">

**Vidrensic — reconstruct the recording, preserve the evidence.**

</div>
