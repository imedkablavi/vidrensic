<div align="center">

<img src="docs/assets/vidrensic-mark.svg" width="116" alt="Vidrensic logo">

# Vidrensic

**Forensic-first DVR / NVR evidence reconstruction and video forensics**

Acquire · Triage · Detect · Reconstruct · Validate · Audit

[![CI](https://github.com/imedkablavi/vidrensic/actions/workflows/ci.yml/badge.svg)](https://github.com/imedkablavi/vidrensic/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/imedkablavi/vidrensic?include_prereleases&sort=semver)](https://github.com/imedkablavi/vidrensic/releases)
![Version](https://img.shields.io/badge/package-0.5.0a0-2563eb)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Linux-111827?logo=linux)
![Coverage gate](https://img.shields.io/badge/coverage%20gate-70%25-16a34a)
![License](https://img.shields.io/badge/license-Proprietary-b91c1c)
[![Stars](https://img.shields.io/github/stars/imedkablavi/vidrensic?style=flat&logo=github)](https://github.com/imedkablavi/vidrensic/stargazers)

**Recover what the recorder still contains without pretending uncertainty is certainty.**

[Demo](docs/DEMO.md) · [Support matrix](docs/SUPPORT_MATRIX.md) · [Validation](docs/VALIDATION.md) · [Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

</div>

<img src="docs/assets/vidrensic-hero.svg" width="100%" alt="Vidrensic forensic video platform">

> **Status — 0.5 alpha.** Vidrensic is under active forensic validation. It is not independently certified and must not be represented as a validated replacement for an organization’s required forensic procedures. Unsupported, ambiguous and unvalidated operations are deliberately surfaced instead of being hidden behind success-looking output.

## Why Vidrensic exists

Surveillance evidence often survives after the recorder index does not. DVR/NVR storage can use proprietary circular layouts, interleave cameras, fragment recordings, change logical channel slots, contain partial overwrites, or mix ordinary filesystems with raw video regions.

Vidrensic treats these as **evidence reconstruction problems**, not ordinary file recovery.

```text
Recorder / OEM variant
        ↓
Storage topology + filesystem family
        ↓
Index / allocation evidence
        ↓
Record / container framing
        ↓
Codec + native timestamp evidence
        ↓
Reconstruction strategy
        ↓
Validation + provenance
```

## What makes it different

- **Capability stages instead of one misleading “supported” flag.** Detection, profiling, parsing, reconstruction and validation are separate maturity levels.
- **Read-only evidence handling first.** Mounted or write-enabled block devices are rejected by default before parser work.
- **Format + firmware variant awareness.** Vendor branding, filesystem, container, codec and timestamp evidence are kept separate.
- **Ambiguity stays visible.** Competing fragment paths, uncertain camera identity and missing timestamps are not silently guessed.
- **Native and derived data stay separate.** Native payloads, review derivatives, corrected time and crypto transforms carry independent provenance.
- **Recovery is treated as adversarial parsing.** Bounds, malformed input, interrupted acquisition, concurrency and corrupted metadata are part of QA.
- **A public demo needs no real CCTV.** The repository includes deterministic synthetic recorder data for repeatable testing.

## 60-second start

```bash
git clone https://github.com/imedkablavi/vidrensic.git
cd vidrensic
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'

vidrensic --version
vidrensic doctor
vidrensic formats list
```

### Try it without real evidence

```bash
bash examples/run_demo.sh
```

The demo creates a deterministic synthetic DHAV-like source, ranks format evidence, recovers structurally valid frames into two physical channels and emits a forensic manifest. The demo itself is regression-tested so it cannot silently rot as parsers evolve.

Full walkthrough: [`docs/DEMO.md`](docs/DEMO.md).

## Core workflow

```text
SOURCE
  ↓
source inspect / SMART / storage map
  ↓
triage + ranked format evidence
  ↓
acquisition / verified image
  ↓
format-specific profiling
  ↓
reconstruction / native extraction
  ↓
QC + provenance
  ↓
review / export (roadmap)
```

Triage an unknown image without modifying it:

```bash
vidrensic triage evidence.raw --out triage.json
vidrensic formats detect evidence.raw --json
```

Inspect a block device before touching it:

```bash
vidrensic source inspect /dev/sdX --json
```

## Capability matrix

Vidrensic does not use a single `supported=true` flag. The live capability output is authoritative:

```bash
vidrensic formats list
vidrensic formats list --json
```

| Family | Stage | Implemented now | Explicit limitation |
|---|---:|---|---|
| **WFS** | `RECONSTRUCT` | detection, profiling, date scan, observed WFS framing, conservative local fragment-chain recovery, codec-neutral native extraction, QC hooks | WFS path-dependent global solving and frame-level partial-overwrite salvage remain incomplete |
| **DHAV** | `RECONSTRUCT` | validated headers/footers, extension metadata, channel/frame/timestamp parsing, bounded streaming scan, physical-order channel demux, hashes | circular-wrap chronology and broader variant/audio validation remain incomplete |
| **Hikvision proprietary** | `PROFILE` | `HIKVISION@HANGZHOU` Master Sector discovery and bounded geometry plausibility analysis | HIKBTREE/data-block recovery is not yet claimed |
| **Annex-B H.264/H.265** | `PARSE` | NAL/parameter-set evidence and codec hints | raw NAL units do not prove recorder identity or wall-clock time |
| **MPEG-PS/PES** | `PARSE` | program-stream/PES detection and generic media handoff | vendor metadata/timestamp variants still require profiles |
| **Known filesystems** | `PROFILE` | MBR/GPT plus EXT/XFS/JFS/FAT/NTFS/exFAT/Btrfs/HFS+ signatures without mounting | finding a filesystem does not prove where recordings live |

See [`docs/SUPPORT_MATRIX.md`](docs/SUPPORT_MATRIX.md) for failure-mode coverage.

## Unknown-recorder triage

```bash
vidrensic triage /dev/sdX \
  --out triage.json \
  --sample-size 4MiB \
  --sample-count 5
```

A triage run combines bounded source sampling, storage profiling, ranked format detection and streaming signature mapping. Its job is to answer **what should be investigated next**, not to force a format classification.

For a dedicated physical signature map:

```bash
vidrensic profile hitmap evidence.raw \
  --range-size 2GiB \
  --out hitmap.json
```

## Acquisition and verification

Plan or run GNU ddrescue while retaining its resumable map:

```bash
vidrensic acquire plan /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map

vidrensic acquire run /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map \
  --case /cases/CASE-001
```

Verify the resulting image/map and emit a receipt:

```bash
vidrensic acquire verify /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map \
  --receipt acquisition-receipt.json
```

Receipts distinguish finished, bad-sector, non-tried, non-trimmed and non-scraped map regions; preserve source/range geometry; and can hash both map and output. An unresolved or unhashed acquisition is not silently labelled complete.

## WFS workflow

Profile uncertain alignment first:

```bash
vidrensic profile wfs-layout evidence.raw \
  --range-size 64MiB \
  --out wfs-layout.json
```

After validating a candidate data-area offset, scan a date:

```bash
vidrensic scan evidence.raw \
  --plugin wfs \
  --date 2030-01-02 \
  --data-offset 67108864
```

Recover one synthetic/example simultaneous boundary:

```bash
vidrensic recover wfs evidence.raw \
  --starts 0,1,2,3 \
  --stop-fragment 4096 \
  --out recovered/example-boundary \
  --label 2030-01-02_example \
  --data-offset 67108864
```

The values above are documentation examples, not a universal WFS geometry. Real offsets/start fragments must come from evidence and profiling.

Codec naming is evidence-driven. Strong H.264 parameter-set evidence produces `.h264`, strong HEVC evidence produces `.h265`, and uncertain elementary video remains `.es` with a review reason.

## DHAV workflow

```bash
vidrensic formats detect recorder-image.raw --json
vidrensic recover dhav recorder-image.raw --out recovered/dhav
```

Native DHAV frames are preserved by channel and elementary-stream derivatives are hashed. Physical ordering is preserved; it is **not** automatically presented as chronological order across a circular wrap.

## Known-key encrypted data

Vidrensic includes an auditable cryptographic primitive layer, not a universal “decrypt DVR” button.

```bash
vidrensic decrypt aes encrypted.bin \
  --output decrypted.bin \
  --mode cbc \
  --key-file key.bin \
  --iv-hex 00112233445566778899aabbccddeeff \
  --padding pkcs7 \
  --receipt crypto-receipt.json
```

Current primitives include AES-CBC and AES-CTR with 128/192/256-bit **known keys**. Receipts record key fingerprints and transform metadata, never key bytes. Vendor-specific key discovery/derivation is not claimed unless a format profile explicitly implements and validates it.

## Time evidence

Recorder-native time and corrected/reference time are separate evidence classes. Unknown recorder timezone remains unknown. Clock correction is derived from explicit anchors and records offset/drift/residual information rather than replacing native timestamps.

## Reconstruction engine

The format-neutral recovery layer includes a node-disjoint global solver foundation for competing fragment paths. It can optimize supplied graph hypotheses across multiple starts and estimate an alternative-solution margin.

That does **not** mean every format automatically uses global solving. WFS still needs a validated path-dependent state graph before the global solver can replace all local continuation logic.

## Validation states

| State | Meaning |
|---|---|
| `PASS` | Required validation actually ran and no unresolved hard condition remains |
| `REVIEW` | Candidate exists but ambiguity, missing evidence or a diagnostic concern remains |
| `FAIL` | Structural, decoding, timing or integrity evidence is strongly inconsistent |
| `UNKNOWN` | Required validation has not run |

Duration alone is never treated as a PASS.

## QA and release gates

Normal CI runs on Python 3.11, 3.12 and 3.13 and currently gates:

```text
ruff
compileall
unit + synthetic regression tests
malformed-input safety tests
coverage >= 70%
CLI smoke tests
package import tests
sdist + wheel build
pip dependency checks
fresh installation of the built wheel
built-wheel smoke tests
public synthetic demo regression
```

Additional security automation audits Python dependencies and public-release hygiene.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) and [`docs/RELEASE_NOTES_0.5.md`](docs/RELEASE_NOTES_0.5.md).

## Repository map

```text
vidrensic/
├── acquisition/       source safety, SMART, ddrescue maps + receipts
├── core/              case, audit, jobs, provenance, time and hashes
├── crypto/            audited known-key crypto primitives
├── io/                file/JBOD/RAID0 random-access readers
├── media/             ffprobe/decode QC + elementary stream helpers
├── profiler/          source, storage, hit-map and triage analysis
├── profiles/          model/firmware data profiles
├── plugins/           WFS, DHAV, Hikvision, Annex-B, MPEG-PS
└── recovery/          graph + global solver foundations

examples/              deterministic synthetic public demo
docs/                  architecture, support, demo, validation, release docs
.github/                CI, security, issue forms and contribution workflow
CITATION.cff            citation metadata for research/tool references
```

## Forensic safety rules

1. Never repair the evidence source.
2. Prefer a hardware write blocker; software read-only checks are an additional control.
3. Reject mounted/write-enabled block sources by default.
4. Preserve native artifacts and hashes separately from review copies.
5. Treat signatures as evidence, not certainty.
6. Preserve ambiguity instead of inventing camera/fragment identity.
7. Never invent missing timestamps or timezone evidence.
8. Bound parser-controlled lengths, offsets and table counts.
9. Never store cryptographic key bytes in logs or receipts.
10. Do not advertise a family/model as recoverable when only detection or profiling exists.

## Contributing

High-value contributions include synthetic/legal fixtures, corruption cases, format documentation, test vectors, safety hardening and reproducible bug reports. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md).

Have a recorder/firmware variant Vidrensic does not understand yet? Use the **New DVR / NVR format request** issue form and read [`docs/SAMPLE_SUBMISSION.md`](docs/SAMPLE_SUBMISSION.md) before sharing sample material.

Never upload active-case CCTV, credentials, encryption keys or evidence you are not authorized to redistribute.

Security issues should follow [`SECURITY.md`](SECURITY.md), not a public issue.

Research users can cite the project through [`CITATION.cff`](CITATION.cff).

If Vidrensic is useful to your research or lab work, a GitHub star helps other practitioners discover the project.

## Roadmap

Near-term priorities:

- WFS path-dependent global reconstruction graph;
- frame-level partial-overwrite salvage;
- DHAV chronological circular-wrap reconstruction and audio validation;
- Hikvision HIKBTREE/data-block variant parsers backed by real fixtures;
- E01/Ex01/AFF4 adapter strategy with independent verification;
- RAID parity and recorder-specific multi-disk hypotheses;
- synchronized multi-camera review workstation;
- forensic export/report packages and stronger signed provenance;
- larger known-good + intentionally corrupted validation corpus.

Full roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Ownership and license

Project owner / lead developer: [`@imedkablavi`](https://github.com/imedkablavi)

Copyright © 2026 imedkablavi. All rights reserved.

Vidrensic is currently proprietary software. Repository visibility does not by itself grant permission to redistribute, sublicense, sell, publish, host or incorporate the source into another product. See [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md) and [`AUTHORS.md`](AUTHORS.md).

Public-launch settings and owner-only decisions are tracked in [`docs/PUBLIC_LAUNCH.md`](docs/PUBLIC_LAUNCH.md).

---

<div align="center">

**Vidrensic — reconstruct the recording, preserve the evidence.**

</div>
