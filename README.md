# Cybrex Video Forensics

**Cybrex Video Forensics (CVF)** is a Linux-first forensic platform for acquisition, reconstruction, validation, review, and export of proprietary DVR/NVR surveillance video.

> Status: **0.1.0-alpha architecture bootstrap**. This repository is intentionally separate from the stable `WFS-5.0` recovery repository.

## Product direction

CVF is being designed as a forensic case platform rather than a single-format recovery script. WFS is the first recovery plugin, with a plugin architecture intended to support additional proprietary DVR/NVR filesystems and container variants over time.

Core goals:

- preserve source evidence and default to read-only workflows;
- make every destructive or evidence-affecting action explicit and auditable;
- hash sources, acquisitions, recovered native streams, and exported review copies;
- support resumable acquisition using GNU ddrescue maps;
- separate native evidence, reconstructed streams, playable proxies, and analyst decisions;
- reconstruct fragmented/deleted/inaccessible recordings using multiple independent evidence signals;
- preserve original timing evidence instead of inventing missing timestamps;
- provide deterministic QC with clear PASS / REVIEW / FAIL reasons;
- provide synchronized multi-camera review, timeline navigation, thumbnails, bookmarks, and controlled export;
- generate reproducible technical and chain-of-custody reports;
- expose both CLI and future workstation/API interfaces from the same forensic core.

## High-level architecture

```text
Evidence source
   |
   v
Acquisition engine -----> source hashes / SMART / ddrescue map / audit
   |
   v
Format profiler -----> plugin registry
   |
   +---- WFS plugin
   +---- future DVR/NVR plugins
   |
   v
Fragment / recording reconstruction
   |
   v
Native stream extraction -----> timestamp sidecars
   |
   v
Media validation / corruption map / keyframe map
   |
   +---- forensic master
   +---- playable review proxy
   |
   v
Review workstation -----> KEEP / REVIEW / bookmarks / notes
   |
   v
Evidence export -----> hashes / manifest / HTML/PDF reports
```

## Development principles

1. **Fail closed.** Ambiguous evidence is REVIEW, not PASS.
2. **Never modify the evidence source.** Device acquisition requires read-only verification or an explicit override recorded in the audit trail.
3. **Native first.** Prefer extraction/stream-copy over transcoding when technically safe.
4. **No invented time.** Missing proprietary timestamp data remains missing unless an analyst explicitly creates a derived/interpolated timeline.
5. **Reproducible jobs.** Parameters, tool versions, hashes, and outputs are recorded.
6. **Separation of evidence and convenience copies.** Review proxies are derived artifacts and are never presented as native evidence.
7. **Plugin isolation.** Proprietary filesystem/container knowledge lives in plugins instead of leaking into the case engine.

## Planned CLI

```bash
cvf case create CASE-2026-001 --root /cases
cvf source inspect /dev/sdb
cvf acquire /dev/sdb --case /cases/CASE-2026-001 --mode ddrescue
cvf plugins list
cvf scan --case /cases/CASE-2026-001 --plugin auto
cvf recover --case /cases/CASE-2026-001 --date 2026-08-09
cvf review --case /cases/CASE-2026-001
cvf export --case /cases/CASE-2026-001 --profile forensic-master
```

The CLI will only expose features once their safety checks and regression tests are in place.

## Repository layout

```text
cvf/                    Python package
  acquisition/          source inspection and acquisition planning
  core/                 case, audit, hashes, immutable models
  media/                probing and validation helpers
  plugins/              DVR/NVR format plugins
    wfs/                 WFS plugin
  recovery/             reconstruction models and graph logic
docs/                   architecture and forensic design documents
tests/                  regression/unit tests
.github/workflows/       CI
```

## Current milestone

The first milestone establishes the forensic foundation before migrating the existing WFS recovery logic:

- case model;
- hash helpers;
- append-only hash-chained audit log;
- Linux block-device read-only inspection;
- safe ddrescue command planning;
- plugin API and registry;
- initial WFS signatures/timestamp codec;
- media probing abstraction;
- reconstruction graph data model;
- automated tests and CI.

See `docs/ROADMAP.md` and `docs/ARCHITECTURE.md` for the migration plan.

## Forensic notice

CVF is under active development. An alpha build must not be represented as validated forensic software without organization-specific validation, documented procedures, known-good test media, and independent verification of results.
