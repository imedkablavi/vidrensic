<div align="center">

# VIDRENSIC

### DVR / NVR Evidence Reconstruction & Video Forensics

**Acquire · Profile · Detect · Reconstruct · Validate · Review · Export**

![Stage](https://img.shields.io/badge/stage-0.4--alpha-orange)
![Platform](https://img.shields.io/badge/platform-Linux-222222?logo=linux)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-Proprietary-red)
![Evidence](https://img.shields.io/badge/source-read--only%20first-0A7B83)
![Families](https://img.shields.io/badge/architecture-multi--format-6f42c1)

**Forensic-first recovery for proprietary surveillance storage.**

</div>

---

## The problem Vidrensic is built for

Surveillance disks often do not behave like ordinary computer filesystems. A DVR/NVR may use a proprietary circular store, split one camera across thousands of fragments, interleave several channels, lose its index while video remains intact, change channel-slot ordering between recording intervals, store native timestamps outside the media payload, or contain a known Linux filesystem next to a raw proprietary video area.

Vidrensic is designed around those failure modes rather than around one recorder brand.

```text
Retail DVR/NVR model
        ↓
Firmware / OEM variant
        ↓
Storage family
        ↓
Index / allocation structure
        ↓
Record / container family
        ↓
Codec + native timestamp variant
        ↓
Recovery strategy + validation evidence
```

That separation matters: two different brands may share an OEM storage format, while two models from the same brand may use different storage generations.

> **Current release:** `0.4.0-alpha`. Core acquisition, WFS reconstruction, DHAV frame/channel recovery, source/storage profiling, media QC and selected format detection are implemented. The project remains under forensic validation and must not yet be represented as independently certified forensic software.

---

## Current format capability matrix

Vidrensic deliberately does **not** use a single misleading “supported” flag. Each family reports the highest implemented stage plus the concrete operations it can perform.

| Family | Stage | What works now | Main limitation |
|---|---:|---|---|
| **WFS** | `RECONSTRUCT` | Detection, WFS timestamps/records, date scan, multi-stream fragment reconstruction, native HEVC extraction | Current framing is validated against the project corpus; global graph solving and frame-level overwrite salvage are pending |
| **DHAV** | `RECONSTRUCT` | Header/footer validation, channel/frame/timestamp parsing, bounded carve, physical-order channel demux, native/ES hashes | Circular-wrap chronological solving and more extension variants are pending |
| **Hikvision proprietary** | `PROFILE` | Dynamic `HIKVISION@HANGZHOU` Master Sector discovery and geometry plausibility analysis | HIKBTREE/data-block recording recovery is not claimed yet |
| **Annex-B H.264/H.265** | `PARSE` | Stream-level detection by NAL/parameter-set evidence | No recorder/vendor or wall-clock identity is inferred from raw NAL units |
| **MPEG-PS/PES** | `PARSE` | Program-stream/PES detection and generic media-layer handoff | Vendor timestamp/metadata variants require profiles |
| **Known filesystems** | `PROFILE` | MBR/GPT + EXT/XFS/JFS/FAT/NTFS/exFAT/Btrfs/HFS+ signatures without mounting | A known filesystem does not prove where the surveillance video is stored |

Run the live matrix from the installed build:

```bash
vidrensic formats list
vidrensic formats list --json
```

See [`docs/SUPPORT_MATRIX.md`](docs/SUPPORT_MATRIX.md) for failure-mode coverage and research targets such as WFH, IFS variants, Stream/Stream_db, TangoMagic, HIK/HIKSql generations, additional DHFS variants, TDFS, BJPEG, JDAT, Milefs and OEM/white-label recorder families.

---

## Fail closed, not confident-looking

Vidrensic distinguishes maturity and operations:

```text
NONE → DETECT → PROFILE → PARSE → RECONSTRUCT → VALIDATE → EXPORT
```

A family can be recognized without being recoverable. For example, the current Hikvision implementation can profile a Master Sector but cannot yet claim validated HIKBTREE recording recovery.

Operations are tracked separately:

```text
detect
profile
date-scan
stream-parse
native-recover
channel-demux
media-qc
forensic-export
```

If an operation is unavailable, the CLI rejects it explicitly. It does not convert “not implemented” into an empty result.

---

## Ranked format detection

Unknown media is evaluated by every active family plugin. Results include confidence and the evidence that produced it.

```bash
vidrensic formats detect evidence.raw
vidrensic formats detect evidence.raw --json
```

Automatic selection is blocked when:

- the best confidence is below the minimum threshold; or
- the best and second-best formats are too close.

This prevents a raw H.264 signature inside a proprietary DVR store from automatically overriding stronger filesystem/record evidence.

---

## Forensic pipeline

```text
┌───────────────────────────────────────┐
│ Evidence Source                       │
│ disk · image · clone · bounded range  │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Source Safety & Identity              │
│ RO state · mounts · SMART · geometry  │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Storage / Evidence Profiling          │
│ MBR/GPT · FS hits · hashes · entropy  │
│ signatures · alignment hypotheses     │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Acquisition                           │
│ ddrescue · selective ranges · resume  │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Ranked Format + Variant Resolution    │
│ WFS · DHAV · HIK · Annex-B · PS · …   │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Reconstruction                        │
│ index · timestamps · fragment graph   │
│ channel demux · frame salvage         │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Native Extraction                     │
│ original payloads · metadata · hashes │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ QC / Validation                       │
│ ffprobe · decode · timing · ambiguity │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Review Workstation                    │
│ matrix · timeline · preview · KEEP    │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Evidence Export                       │
│ native · review · manifest · report   │
└───────────────────────────────────────┘
```

---

## Problems the architecture is designed to handle

- missing or corrupt recorder index;
- deleted/unindexed recordings whose data remains on disk;
- circular recording stores and wrap points;
- multiple cameras interleaved in one physical region;
- channel/slot mapping that changes over time;
- fragmented recordings;
- partial/truncated records;
- bad-sector gaps and interrupted acquisitions;
- partially overwritten recordings;
- timestamp gaps, backwards jumps and clock drift;
- wrong interpreted FPS or playback duration;
- broken MP4/MOV seek indexes;
- damaged GOPs and missing codec parameter sets;
- mixed codec/firmware variants;
- proprietary container metadata;
- unknown OEM/white-label recorders.

Not all of these have reached production-capable implementation yet. [`docs/SUPPORT_MATRIX.md`](docs/SUPPORT_MATRIX.md) states which failure modes are currently implemented per family.

---

## Case-first workflow

### 1. Create a case

```bash
vidrensic case create CASE-2026-001 \
  --root /cases \
  --examiner "Examiner"
```

A case keeps evidence metadata, acquisitions, native/review derivatives, jobs, logs, reports and exports separated.

### 2. Inspect source safety

```bash
vidrensic source inspect /dev/sdb --json
```

Block devices are expected to be read-only and unmounted. Child partitions are checked too.

### 3. Capture SMART/device identity

```bash
vidrensic source smart /dev/sdb \
  --out /cases/CASE-2026-001/evidence/source-smart.json \
  --case /cases/CASE-2026-001
```

### 4. Map conventional storage without mounting it

```bash
vidrensic profile storage /dev/sdb \
  --out /cases/CASE-2026-001/evidence/storage-map.json \
  --case /cases/CASE-2026-001
```

### 5. Build a bounded generic profile

```bash
vidrensic profile source /dev/sdb \
  --sample-size 4194304 \
  --sample-count 5 \
  --out /cases/CASE-2026-001/evidence/source-profile.json \
  --case /cases/CASE-2026-001
```

### 6. Rank active format families

```bash
vidrensic formats detect /dev/sdb --json
```

### 7. Acquire safely with ddrescue

```bash
vidrensic acquire plan /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/range.raw \
  --map /cases/CASE-2026-001/acquisitions/range.map \
  --offset 1122820554752 \
  --size 12582912000

vidrensic acquire run /dev/sdb \
  --output /cases/CASE-2026-001/acquisitions/range.raw \
  --map /cases/CASE-2026-001/acquisitions/range.map \
  --offset 1122820554752 \
  --size 12582912000 \
  --case /cases/CASE-2026-001
```

The GNU ddrescue map is retained for resume. Vidrensic does not repair the source filesystem.

---

## WFS workflow

Profile an uncertain alignment before assuming a data layout:

```bash
vidrensic profile wfs-layout evidence.raw \
  --range-start 0 \
  --range-size 67108864 \
  --out wfs-layout.json
```

The result intentionally distinguishes:

```text
fragment alignment residue ≠ proven absolute WFS data-area start
```

Scan a known/validated WFS layout:

```bash
vidrensic scan evidence.raw \
  --plugin wfs \
  --date 2026-08-09 \
  --data-offset 64094208
```

Recover one simultaneous recording boundary:

```bash
vidrensic recover wfs evidence.raw \
  --starts 0,1,2,4 \
  --stop-fragment 1744 \
  --out recovered/09-00 \
  --label 2026-08-09_09-00 \
  --data-offset 64094208
```

Outputs use neutral candidate IDs. A reconstruction slot is never silently promoted to a physical camera identity.

---

## DHAV workflow

Detect DHAV evidence:

```bash
vidrensic formats detect dahua-or-oem.raw
```

Carve validated frames and demultiplex channels while preserving physical ordering:

```bash
vidrensic recover dhav dahua-or-oem.raw \
  --out recovered/dhav
```

Output example:

```text
recovered/dhav/
├── channel_00.native.dhav
├── channel_00.video.es
├── channel_01.native.dhav
├── channel_01.video.es
└── dhav_manifest.json
```

The manifest records physical offsets, frame/channel statistics, timestamp/frame-number discontinuities, codec hints and SHA-256/SHA-512 hashes. Physical order does **not** claim chronological order across a circular wrap.

---

## Hikvision status

The 0.4 profiler dynamically searches for `HIKVISION@HANGZHOU` Master Sector candidates and evaluates capacity, video-data geometry, block geometry, HIKBTREE fields and initialization-time plausibility.

```bash
vidrensic formats detect hikvision-image.raw --json
```

Current capability is intentionally `PROFILE`, not `RECONSTRUCT`. A command requiring a date timeline is blocked until HIKBTREE/data-block variants are implemented and validated.

---

## Model / firmware profiles

Structural support and product-model hints are separated from executable parser code.

```bash
vidrensic profiles list
vidrensic profiles match --vendor Hikvision --model MODEL --firmware VERSION
vidrensic profiles validate-pack new-model-profiles.json
```

External profile packs are JSON data. They do not install arbitrary Python/shell code.

New model onboarding follows [`docs/FORMAT_ONBOARDING.md`](docs/FORMAT_ONBOARDING.md).

---

## Media validation states

| State | Meaning |
|---|---|
| `PASS` | Required validation ran and no hard or unresolved ambiguity remains |
| `REVIEW` | A candidate exists but evidence is incomplete, ambiguous or needs examiner review |
| `FAIL` | Structural, decoding, timing or integrity evidence is strongly inconsistent |
| `UNKNOWN` | Required validation has not yet run |

A one-hour duration alone is never a PASS. A successful beginning/middle/end decode is useful triage evidence but is not a full decode.

```bash
vidrensic qc fast recovered.mp4 \
  --expected-duration 3600 \
  --report qc-fast.json

vidrensic qc full recovered.mp4 \
  --expected-duration 3600 \
  --report qc-full.json
```

---

## Safety rules

1. **Never repair the evidence source.**
2. **Prefer a hardware write blocker; enforce software read-only checks as an additional control.**
3. **Reject mounted/write-enabled block sources by default.**
4. **Record important operations in case audit/job state.**
5. **Treat signatures as evidence, not certainty.**
6. **Preserve ambiguity instead of forcing a camera/fragment match.**
7. **Keep native data separate from review/transcoded copies.**
8. **Never invent missing timestamps.** Derived/corrected timelines must remain labeled as derived.
9. **Bound parser-controlled lengths, offsets and table counts.**
10. **Do not advertise a model as recoverable when only detection/profiling is implemented.**

---

## Repository layout

```text
vidrensic/
├── acquisition/       source safety, SMART and ddrescue
├── core/              case, audit, jobs, hashes and models
├── media/             ffprobe/decode QC
├── profiler/          source and storage profiling
├── profiles/          data-driven model/firmware variants
├── plugins/
│   ├── wfs/
│   ├── dhav/
│   ├── hikvision/
│   ├── annexb/
│   └── mpegps/
└── recovery/          format-neutral reconstruction graph primitives

docs/
├── ARCHITECTURE.md
├── FORENSIC_POLICY.md
├── FORMAT_ONBOARDING.md
├── ROADMAP.md
└── SUPPORT_MATRIX.md

tests/                 synthetic + regression fixtures
.github/workflows/      CI across Python 3.11/3.12/3.13
```

---

## Next engineering milestones

- scalable streaming hit maps for multi-terabyte media;
- WFS absolute data-area discovery using stronger metadata evidence;
- WFS global weighted fragment graph solver;
- frame-level salvage for partial overwrite and bad-sector gaps;
- DHAV circular-wrap chronological reconstruction;
- Hikvision HIKBTREE/data-block parser with firmware profiles;
- WFH/IFS/Stream/TangoMagic family research and fixtures;
- decoder/keyframe/corruption maps;
- RAID/JBOD and multi-disk recorder source sets;
- synchronized multi-camera review workstation;
- sticky preview, thumbnails, frame stepping, ±5s seek and high-speed playback;
- safe KEEP/review/cleanup workflow;
- native vs review-copy export profiles;
- signed manifests, HTML/PDF technical reports and chain-of-custody packages;
- formal validation corpus and release qualification.

---

## Ownership & licensing

**Project owner / lead developer:** `@imedkablavi`

Copyright © 2026 imedkablavi. All rights reserved.

Vidrensic is **proprietary software**. Repository access does not grant permission to redistribute, sublicense, sell, publish, host, or incorporate the source into another product. See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md) and [`AUTHORS.md`](AUTHORS.md).

The current product name is a working commercial identity. Initial public searching did not reveal an obvious exact software-name conflict, but this is not formal trademark clearance. Commercial launch should include legal/trademark review.

---

## Validation notice

Functional code is not sufficient for forensic qualification. Production/evidentiary use requires versioned known-good and deliberately corrupted media, documented expected results, hashes, parser limits, repeatability tests and organization-specific validation procedures.

<div align="center">

**Vidrensic — reconstruct the recording, preserve the evidence.**

</div>
