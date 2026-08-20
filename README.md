<div align="center">

# VIDRENSIC

### DVR / NVR Evidence Reconstruction & Video Forensics

**Acquire. Profile. Reconstruct. Validate. Review. Export.**

![Stage](https://img.shields.io/badge/stage-0.3--alpha-orange)
![Platform](https://img.shields.io/badge/platform-Linux-222222?logo=linux)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-Proprietary-red)
![Evidence](https://img.shields.io/badge/evidence-read--only%20first-0A7B83)

**A forensic-first platform for proprietary surveillance storage.**

</div>

---

## What is Vidrensic?

Vidrensic is a Linux-first forensic platform for recovering and examining video from proprietary DVR/NVR storage systems where ordinary filesystem undelete and generic file carving are not enough.

It is designed around the reality of surveillance evidence: interleaved camera fragments, overwritten metadata, proprietary timestamps, partial recordings, damaged media, unstable camera-slot ordering, unknown data areas, unusual codecs, and source disks that should be treated as evidence rather than repaired in place.

The project is intentionally broader than one filesystem. **WFS is the first recovery plugin**, while the core is being built to support additional DVR/NVR layouts through isolated forensic plugins and an evidence-source profiler.

> **Current status:** `0.3.0-alpha`. Acquisition, case/audit/job state, WFS reconstruction/native recovery, media QC, SMART capture and bounded source profiling are implemented but still undergoing forensic validation. The project must not yet be represented as independently validated forensic software.

---

## Why this project exists

Traditional recovery tools usually answer: “Can I find a file?”

Vidrensic must answer harder questions:

- Which physical fragments belong to the same recording?
- Which fragments belong to different cameras recorded at the same time?
- Is a one-hour output actually one coherent camera stream?
- Was part of the recording overwritten or merely unindexed?
- Is the timestamp native evidence or a derived estimate?
- Can the recovered stream decode at the beginning, middle, and end?
- Which source-layout conclusion is proven, and which is only a hypothesis?
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
│ Safety / Identity / Profile  │
│ RO • SMART • hashes • sample │
│ signatures • hypotheses      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Acquisition                  │
│ ddrescue • ranges • resume   │
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
| Case engine | ✅ | Structured case directories, UUID, examiner identity and case schema |
| Audit | ✅ | Append-only JSONL events with SHA-256 hash chaining and verification |
| Persistent jobs | ✅ | SQLite WAL job database, state transitions, progress and checkpoints |
| Hashing | ✅ | SHA-256/SHA-512 streaming hashes |
| Linux source inspection | ✅ | File/block-device size, RO state, source/child mount detection |
| SMART evidence snapshot | ✅ | Device identity, health indicators and preserved `smartctl` JSON |
| Bounded source profiler | ✅ | Reproducible sample hashes, entropy and surveillance/container signatures |
| WFS alignment profiler | 🧪 | Evidence-ranked 2 MiB fragment residue hypotheses; no fake data-offset claim |
| Acquisition planning | ✅ | GNU ddrescue ranges, map files, resume-aware capacity checks |
| Acquisition execution | 🧪 | Controlled subprocess execution; no shell interpolation |
| Plugin framework | ✅ | Isolated format plugin API and registry |
| WFS timestamps | ✅ | Decode/encode support for observed WFS timestamp words |
| WFS record parser | ✅ | FD/FE/FC/FA/F9 framing with conservative length validation |
| WFS timeline scan | ✅ | Fragment-boundary recording-start discovery by date |
| WFS reconstruction | 🧪 | Conservative multi-stream continuation with physical-fragment mutual exclusion |
| Native HEVC recovery | 🧪 | Neutral candidates, hashes, reconstruction evidence and JSON manifest |
| Media probing | ✅ | Structured ffprobe integration |
| Fast QC | ✅ | Beginning/middle/end decoding; clean result remains REVIEW, never false PASS |
| Full-decode QC | 🧪 | Full first-video-stream decode plus timing/reconstruction evidence policy |
| Review workstation | 🚧 | Next major product surface |
| Court/report package | 🚧 | Planned after case/export schema stabilizes |

Legend: ✅ implemented • 🧪 implemented but still being validated • 🚧 planned/in progress

---

## Safety model

Vidrensic follows several non-negotiable rules:

1. **The evidence source is never repaired or mounted by Vidrensic.**
2. **Block devices are expected to be read-only and unmounted.** Mounted child partitions are detected too. Write-enabled devices are rejected unless an explicit forensic override is used and audited.
3. **A signature is not a verdict.** Profiler results remain hypotheses until stronger structural evidence supports them.
4. **Ambiguity is preserved.** A technically playable result is not automatically a forensic PASS.
5. **Native evidence and review proxies remain separate.**
6. **Original timestamps are preserved.** Derived/interpolated time must be labeled as derived.
7. **Destructive actions are opt-in.** Cleanup/export decisions never silently modify source evidence.
8. **Long jobs are case state, not terminal state.** Parameters, checkpoints and final status live in the case database.
9. **Every important operation is intended to be reproducible from logged parameters and hashes.**

---

## CLI — implemented workflow

```bash
# Create a case
vidrensic case create CASE-2026-001 \
  --root /cases \
  --examiner "Examiner"

# Inspect source safety
vidrensic source inspect /dev/sdb

# Capture SMART/device identity
vidrensic source smart /dev/sdb \
  --out /cases/CASE-2026-001/evidence/source-smart.json \
  --case /cases/CASE-2026-001

# Build a bounded profile of an unknown DVR/NVR source.
# This samples; it does NOT claim to have scanned the complete disk.
vidrensic profile source /dev/sdb \
  --sample-size 4MiB \
  --sample-count 5 \
  --out /cases/CASE-2026-001/evidence/source-profile.json \
  --case /cases/CASE-2026-001

# Rank WFS fragment-alignment hypotheses inside a chosen bounded range.
vidrensic profile wfs-layout /dev/sdb \
  --range-start 0 \
  --range-size 64MiB \
  --out /cases/CASE-2026-001/evidence/wfs-layout.json \
  --case /cases/CASE-2026-001

# Build a selective ddrescue acquisition plan
vidrensic acquire plan /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/day09.raw \
  --map /cases/CASE-2026-001/acquisitions/day09.map \
  --offset 1122820554752 \
  --size 12582912000

# Execute it. The ddrescue map remains resumable.
vidrensic acquire run /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/day09.raw \
  --map /cases/CASE-2026-001/acquisitions/day09.map \
  --offset 1122820554752 \
  --size 12582912000 \
  --case /cases/CASE-2026-001

# Scan WFS recording starts
vidrensic scan /cases/CASE-2026-001/acquisitions/day09.raw \
  --plugin wfs \
  --date 2026-08-09

# Recover one simultaneous WFS recording boundary.
# Candidate numbers are neutral reconstruction IDs, not physical camera IDs.
vidrensic recover wfs /cases/CASE-2026-001/acquisitions/day09.raw \
  --starts 0,1,2,4 \
  --stop-fragment 1744 \
  --out /cases/CASE-2026-001/derived/native/09-00 \
  --label 2026-08-09_09-00 \
  --case /cases/CASE-2026-001

# Fast review-oriented integrity check: cannot return PASS.
vidrensic qc fast recovered.mp4 \
  --expected-duration 3600 \
  --report qc-fast.json \
  --case /cases/CASE-2026-001

# Full decode. PASS is possible only when mandatory evidence is satisfied.
vidrensic qc full recovered.mp4 \
  --expected-duration 3600 \
  --report qc-full.json \
  --case /cases/CASE-2026-001

# Inspect persistent jobs/checkpoints
vidrensic jobs list --case /cases/CASE-2026-001
```

> Numeric CLI sizes currently accept Python-style integers such as `67108864` or `0x4000000`. Human suffixes such as `64MiB` are a planned parser improvement and are shown above as the intended commercial UX, not yet the accepted alpha syntax.

---

## Profiling without overclaiming

The source profiler reads bounded reproducible samples and records their absolute offsets, sizes and SHA-256 hashes. It can count known indicators such as WFS version strings, DHAV records and Annex-B codec markers without uploading source bytes.

The WFS layout profiler separately scores sector-aligned fragment residues using structural record starts, timestamped FD evidence and weak padding evidence. Its output explicitly states that:

```text
fragment residue ≠ absolute WFS data-area start
```

A low-confidence or closely competing result requires more sampling or format-specific metadata analysis.

---

## WFS recovery output

A WFS recovery does not silently rename slots as cameras. It produces neutral native candidates and a reconstruction manifest:

```text
derived/native/09-00/
├── 2026-08-09_09-00_candidate_01.hevc
├── 2026-08-09_09-00_candidate_02.hevc
├── 2026-08-09_09-00_candidate_03.hevc
├── 2026-08-09_09-00_candidate_04.hevc
└── 2026-08-09_09-00_recovery_manifest.json
```

The manifest records start fragments, complete fragment chains, ambiguity/unresolved counts, output sizes and cryptographic hashes. A successfully extracted native stream starts as `UNKNOWN` or `REVIEW`; extraction alone never creates a false forensic `PASS`.

---

## Evidence states

| State | Meaning |
|---|---|
| `PASS` | Required validation ran and no hard or ambiguous condition remains |
| `REVIEW` | Candidate exists, but evidence is incomplete, ambiguous, or requires examiner review |
| `FAIL` | Structural, decoding, timing, or integrity evidence is strongly inconsistent |
| `UNKNOWN` | Validation required for a decision has not been performed |

A one-hour duration alone is never sufficient for `PASS`. Likewise, a successful three-point decode is useful for review but is not equivalent to a complete decode.

---

## Repository structure

```text
vidrensic/
├── acquisition/       source inspection, SMART and ddrescue orchestration
├── core/              cases, jobs, models, hashing and audit
├── media/             probing and technical QC
├── profiler/          bounded source fingerprints/hypotheses
├── plugins/
│   └── wfs/           WFS parser, layout, scanner, reconstruction and recovery
└── recovery/          format-neutral graph/reconstruction primitives

docs/                  architecture, forensic policy and roadmap
tests/                 unit + synthetic forensic fixtures
.github/workflows/      CI and regression checks
```

---

## Product roadmap

The next development tracks are:

- WFS absolute data-area discovery with stronger metadata evidence;
- WFS global weighted graph solver;
- frame-level salvage for partially overwritten recordings;
- keyframe and decoder-error maps;
- synchronized multi-camera review matrix;
- sticky preview with frame stepping, ±5s seeking and high-speed review;
- camera-correlation evidence without assuming stable slot order;
- native vs review-copy export profiles;
- signed manifests and case packages;
- HTML/PDF technical and chain-of-custody reporting;
- unknown-DVR plugin SDK;
- synthetic corruption and validation corpus;
- RAID/JBOD and forensic image formats in later commercial milestones.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the engineering sequence.

---

## Ownership & licensing

**Project owner / lead developer:** `@imedkablavi`

Copyright © 2026 imedkablavi. All rights reserved.

This repository is **proprietary software**. Repository access does not grant permission to redistribute, sublicense, sell, publish, or incorporate the source into another product. See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md), and [`AUTHORS.md`](AUTHORS.md).

The product name is a working commercial identity. A basic web search found no obvious software conflict for the exact name during naming, but that is **not** formal trademark clearance. A commercial launch should use proper trademark/legal review.

---

## Validation notice

Forensic software requires more than functional code. Before production or evidentiary use, Vidrensic should be validated against documented known-good and deliberately corrupted test media, with repeatable expected results and version-controlled validation records.

<div align="center">

**Vidrensic — reconstruct the recording, preserve the evidence.**

</div>
