<div align="center">

<img src="docs/assets/vidrensic-mark.svg" width="116" alt="Vidrensic logo">

# Vidrensic

**Forensic-first DVR/NVR evidence reconstruction and video forensics**

Acquire · Triage · Detect · Reconstruct · Validate · Audit

[![CI](https://github.com/imedkablavi/vidrensic/actions/workflows/ci.yml/badge.svg)](https://github.com/imedkablavi/vidrensic/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/imedkablavi/vidrensic?include_prereleases&sort=semver)](https://github.com/imedkablavi/vidrensic/releases)
![Version](https://img.shields.io/badge/package-0.6.0a0-2563eb)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Linux-111827?logo=linux)
![Coverage gate](https://img.shields.io/badge/coverage%20gate-80%25-16a34a)
![License](https://img.shields.io/badge/license-Proprietary-b91c1c)

[Demo](docs/DEMO.md) · [Support matrix](docs/SUPPORT_MATRIX.md) · [Validation](docs/VALIDATION.md) · [Validation corpus](docs/VALIDATION_CORPUS.md) · [Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

</div>

<img src="docs/assets/vidrensic-hero.svg" width="100%" alt="Vidrensic forensic video platform">

> **Status: 0.6 alpha development.** Vidrensic is under active forensic validation. It is not independently certified and must not be represented as a replacement for required forensic procedures. Unsupported, ambiguous, and unvalidated operations are reported explicitly.

## Scope

Vidrensic is built for DVR/NVR storage analysis where ordinary file recovery is not enough. It focuses on read-only acquisition, format detection, storage profiling, reconstruction, provenance, and validation.

Recorder storage can contain proprietary circular layouts, interleaved channels, fragmented recordings, partial overwrites, raw video regions, and damaged indexes. Vidrensic treats those conditions as evidence reconstruction problems.

## Current capabilities

The project separates detection, profiling, parsing, reconstruction, and validation instead of using a single support flag.

| Family | Stage | Implemented | Current limitation |
| --- | --- | --- | --- |
| WFS | `RECONSTRUCT` | detection, profiling, date scan, local reconstruction, experimental path-dependent global solving, physical-fragment exclusion, codec-neutral extraction | broad real-recorder validation and frame/GOP partial-overwrite salvage remain incomplete |
| DHAV | `RECONSTRUCT` | header/footer validation, extension metadata, channel/frame/timestamp parsing, bounded streaming scan, physical-order channel demux, hashes | circular-wrap chronology and broader variant/audio validation remain incomplete |
| Hikvision proprietary | `PROFILE` | Master Sector discovery and bounded geometry plausibility analysis | HIKBTREE/data-block recovery is not claimed |
| Annex-B H.264/H.265 | `PARSE` | NAL/parameter-set evidence and codec hints | raw NAL units do not prove recorder identity or wall-clock time |
| MPEG-PS/PES | `PARSE` | program-stream/PES detection and generic media handoff | vendor metadata and timestamp variants still require profiles |
| Known filesystems | `PROFILE` | MBR/GPT plus EXT/XFS/JFS/FAT/NTFS/exFAT/Btrfs/HFS+ signatures without mounting | filesystem detection does not prove where recordings are stored |

The live capability output is authoritative:

```bash
vidrensic formats list
vidrensic formats list --json
```

See [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md) for detailed failure-mode coverage.

## Installation

Python 3.11, 3.12, and 3.13 are covered by CI.

```bash
git clone https://github.com/imedkablavi/vidrensic.git
cd vidrensic
bash scripts/setup_dev.sh
source .venv/bin/activate

vidrensic --version
vidrensic doctor
vidrensic formats list
```

Run the synthetic demo after setup:

```bash
bash examples/run_demo.sh
```

Or run setup and the demo together:

```bash
bash scripts/setup_dev.sh --demo
```

The public demo and validation corpus use synthetic data. Passing them validates the declared synthetic expectations and test machinery. It does not prove universal real-recorder support.

## Basic workflow

```text
SOURCE
  ↓
source inspection and storage map
  ↓
triage and ranked format evidence
  ↓
acquisition and verified image
  ↓
format-specific profiling
  ↓
reconstruction and native extraction
  ↓
quality control and provenance
  ↓
validation, review, and export
```

Triage an image:

```bash
vidrensic triage evidence.raw --out triage.json
vidrensic formats detect evidence.raw --json
```

Inspect a block device before parser work:

```bash
vidrensic source inspect /dev/sdX --json
```

## Acquisition

Vidrensic can plan and run GNU ddrescue while retaining a resumable map:

```bash
vidrensic acquire plan /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map

vidrensic acquire run /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map \
  --case /cases/CASE-001
```

Verify the resulting image and map:

```bash
vidrensic acquire verify /dev/sdX \
  --output acquisition.raw \
  --map acquisition.map \
  --receipt acquisition-receipt.json
```

Receipts preserve source/range geometry and map state. Unresolved or unhashed acquisition is not silently labelled complete.

## WFS

Profile uncertain layout first:

```bash
vidrensic profile wfs-layout evidence.raw \
  --range-size 64MiB \
  --out wfs-layout.json
```

After validating a candidate data offset:

```bash
vidrensic scan evidence.raw \
  --plugin wfs \
  --date 2030-01-02 \
  --data-offset 67108864
```

Example synthetic recovery:

```bash
vidrensic recover wfs evidence.raw \
  --starts 0,1,2,3 \
  --stop-fragment 4096 \
  --out recovered/example-boundary \
  --label 2030-01-02_example \
  --data-offset 67108864 \
  --strategy global
```

The values above are documentation examples, not universal WFS geometry. Real offsets and start fragments must come from evidence and profiling.

The global strategy is bounded and records ambiguity, search limits, and truncation. A truncated search is review evidence, not proof of an optimum.

## DHAV

```bash
vidrensic formats detect recorder-image.raw --json
vidrensic recover dhav recorder-image.raw --out recovered/dhav
```

Native frames are preserved by channel and derivatives are hashed. Physical ordering is not automatically presented as chronological ordering across a circular wrap.

## Known-key encrypted data

Vidrensic includes known-key cryptographic primitives. It does not claim universal DVR key discovery or decryption.

```bash
vidrensic decrypt aes encrypted.bin \
  --output decrypted.bin \
  --mode cbc \
  --key-file key.bin \
  --iv-hex 00112233445566778899aabbccddeeff \
  --padding pkcs7 \
  --receipt crypto-receipt.json
```

Current primitives include AES-CBC and AES-CTR with 128, 192, or 256-bit known keys. Receipts record key fingerprints and transform metadata, not key bytes.

## Validation states

| State | Meaning |
| --- | --- |
| `PASS` | Required validation ran and no unresolved hard condition remains |
| `REVIEW` | A candidate exists but ambiguity, missing evidence, or a diagnostic concern remains |
| `FAIL` | Structural, decoding, timing, or integrity evidence is strongly inconsistent |
| `UNKNOWN` | Required validation has not run |

Duration alone is never treated as `PASS`. Native extraction alone does not create `PASS`.

Run the public ground-truth corpus:

```bash
vidrensic validate corpus validation_corpus/corpus.json \
  --out validation-report.json
```

See [docs/VALIDATION.md](docs/VALIDATION.md) and [docs/VALIDATION_CORPUS.md](docs/VALIDATION_CORPUS.md) for the validation model.

## Quality gates

Normal CI runs on Python 3.11, 3.12, and 3.13. The Python 3.12 qualification job enforces an overall coverage floor of 80% plus separate thresholds for forensic-critical modules.

CI includes:

- Ruff and compile checks
- unit and synthetic regression tests
- malformed-input safety tests
- coverage gates
- public ground-truth corpus smoke tests
- CLI and package import smoke tests
- source distribution and wheel builds
- dependency checks
- fresh installation of the built wheel
- built-wheel corpus and smoke tests
- repository and Git-history secret checks

Coverage is test evidence, not independent forensic validation.

## Repository map

```text
vidrensic/
├── acquisition/       source safety, SMART, ddrescue maps and receipts
├── core/              case, audit, jobs, provenance, time and hashes
├── crypto/            known-key cryptographic primitives
├── io/                file/JBOD/RAID0 random-access readers
├── media/             ffprobe/decode QC and elementary stream helpers
├── profiler/          source, storage, hit-map and triage analysis
├── profiles/          model and firmware data profiles
├── plugins/           WFS, DHAV, Hikvision, Annex-B, MPEG-PS
├── recovery/          graph and solver foundations
└── validation/        ground-truth corpus runner

validation_corpus/      versioned synthetic/public corpus manifests and fixtures
examples/               deterministic synthetic public demo
docs/                   architecture, support, demo, validation, and release docs
.github/                 CI, security, issue forms, and contribution workflow
CITATION.cff             citation metadata
```

## Forensic safety rules

1. Never repair the evidence source.
2. Prefer a hardware write blocker. Software read-only checks are an additional control.
3. Reject mounted or write-enabled block sources by default.
4. Preserve native artifacts and hashes separately from review copies.
5. Treat signatures as evidence, not certainty.
6. Preserve ambiguity instead of inventing camera or fragment identity.
7. Never invent missing timestamps or timezone evidence.
8. Bound parser-controlled lengths, offsets, and reconstruction search spaces.
9. Never store cryptographic key bytes in logs or receipts.
10. Do not advertise a family or model as recoverable when only detection or profiling exists.
11. A source-hash mismatch invalidates a validation case before recovery runs.

## Documentation

- [Demo](docs/DEMO.md)
- [Support matrix](docs/SUPPORT_MATRIX.md)
- [Validation](docs/VALIDATION.md)
- [Validation corpus](docs/VALIDATION_CORPUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Forensic policy](docs/FORENSIC_POLICY.md)
- [Security gates](docs/SECURITY_GATES.md)
- [Sample submission](docs/SAMPLE_SUBMISSION.md)
- [Licensing strategy](docs/LICENSING_STRATEGY.md)

## Contributing

Useful contributions include synthetic or legally redistributable fixtures, corruption cases, format documentation, test vectors, safety hardening, and reproducible bug reports. See [CONTRIBUTING.md](CONTRIBUTING.md).

Do not upload active-case CCTV, credentials, encryption keys, or evidence you are not authorized to redistribute.

Security reports should follow [SECURITY.md](SECURITY.md), not a public issue.

## License

The current repository is proprietary. See [docs/LICENSING_STRATEGY.md](docs/LICENSING_STRATEGY.md) for the licensing discussion and tradeoffs.
