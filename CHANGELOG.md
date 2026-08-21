# Changelog

All notable Vidrensic development changes are recorded here.

## [0.6.0-alpha] - 2026-08-22

### Added

- Path-dependent WFS global reconstruction mode that preserves branch-specific proprietary carry/tail state before jointly selecting physical-fragment-disjoint paths across simultaneous recording starts.
- Bounded WFS beam hypothesis enumeration with configurable candidate, beam, hypothesis, depth and global-combination limits.
- Global-solution evidence including selected paths, total continuation/cost metrics, unresolved/ambiguous counts, second-best solution information, alternative cost margin, combinations examined and search-truncation state.
- `vidrensic recover wfs --strategy global` CLI workflow; the CLI defaults to global mode while the Python `recover_segment()` API retains the local default for backward compatibility.
- Versioned validation-corpus framework with provenance, redistributability metadata, source SHA-256 ground truth, deterministic expectations and machine-readable expected-vs-actual reports.
- `vidrensic validate corpus` command.
- Initial public synthetic validation corpus under `validation_corpus/`.
- Validation expectation types for source hashes, ranked format detection and WFS recovery.
- Corpus path-confinement, path-traversal rejection, symlink rejection and fail-before-operation behavior on source-hash mismatch.
- Dedicated forensic-critical coverage gate in addition to aggregate coverage.
- Installed-wheel validation-corpus smoke testing in CI.
- New direct regression suites for WFS path hypotheses/global selection, WFS continuation/extraction mechanics, high-level global recovery behavior, validation-corpus safety and ddrescue execution semantics.
- `docs/VALIDATION_CORPUS.md` and `docs/RELEASE_NOTES_0.6.md`.

### Changed

- Raised the aggregate CI coverage floor from 70% to 80%.
- Added independent minimum coverage thresholds for WFS local/global/high-level recovery, the generic solver, hashing, provenance, crypto transforms and ddrescue orchestration.
- WFS recovery manifest schema moved to version 3 and now records reconstruction strategy and global-search evidence.
- Public documentation now distinguishes structurally/synthetically tested WFS global reconstruction from broad real-recorder validation.
- Roadmap and support matrix now treat real-device corpus qualification and independent reruns as separate requirements before `VALIDATE` maturity.
- Development package version advanced to `0.6.0a0`.

### Fixed

- Fixed a WFS continuation-probe boundary bug discovered by the expanded QA suite. Terminal-padding look-ahead could previously read beyond the candidate physical fragment and allow bytes from the following fragment to invalidate an otherwise legitimate continuation. Probe evidence is now capped to the candidate fragment boundary.
- Fixed validation-corpus symlink checking so the symlink directory entry is rejected before `Path.resolve()` dereferences it.

### QA snapshot

At the 0.6 development milestone, the Python 3.12 qualification run reported 131 passing tests and approximately 80.6% aggregate coverage. Critical-module coverage included approximately 85% WFS local reconstruction, 91% WFS path-dependent global reconstruction, 95% WFS high-level recovery, 91% generic global solver, 90% hashing, 92% provenance, 84% known-key crypto and 100% ddrescue orchestration.

The same commit passed CI on Python 3.11, 3.12 and 3.13, Security gates, the public validation corpus and the validation corpus again after installing the built wheel.

These QA results are software-development evidence. They are **not** an independent forensic certification or proof of support for every WFS/DVR/NVR model or firmware.

### Still experimental / incomplete

- Broad multi-device/firmware WFS validation corpus.
- WFS frame/NAL/GOP-level partial-overwrite salvage.
- DHAV circular-wrap chronology and comprehensive audio/firmware variant coverage.
- Hikvision HIKBTREE/data-block reconstruction.
- RAID5/6 parity reconstruction.
- Universal recorder encryption/key recovery.
- Independent lab validation/certification.
- Synchronized graphical review workstation and court-ready signed export packages.

## [0.4.0-alpha] - 2026-08-21

### Added

- Product-level format capability model with explicit `DETECT`, `PROFILE`, `PARSE`, `RECONSTRUCT`, `VALIDATE`, and `EXPORT` stages.
- Storage-topology, recovery-strategy, and failure-mode vocabulary shared across DVR/NVR families.
- Ranked multi-family detection with minimum-confidence and minimum-margin review blocking.
- DHAV 24-byte frame-header / 8-byte footer parser with channel, frame number, packed timestamp, frame length, and Annex-B codec evidence.
- Bounded DHAV carving and per-channel native/elementary demultiplexing with hashes, physical offsets, discontinuity evidence, and forensic manifests.
- Generic raw Annex-B H.264/H.265 detector for stream-level recovery when a proprietary filesystem/index is unavailable.
- Generic MPEG-PS/PES detector for surveillance containers and vendor variants using standard program-stream framing.
- Read-only MBR/GPT mapping and known filesystem profiling for EXT, XFS, JFS, FAT, NTFS, exFAT, Btrfs, and HFS+ without mounting or repairing evidence.
- Data-driven model/firmware variant profile registry and JSON profile-pack validator.
- Hikvision proprietary-storage profiler with dynamic `HIKVISION@HANGZHOU` Master Sector discovery and bounded geometry plausibility checks.
- Synthetic regression tests for DHAV parsing/demux, corrupted DHAV footers, storage maps, ranked detection, profile packs, and Hikvision Master Sector candidates.
- `docs/SUPPORT_MATRIX.md` defining honest family capability and failure-mode coverage.
- `docs/FORMAT_ONBOARDING.md` defining how a new recorder model/firmware family is promoted from research to validated support.

### Changed

- WFS is now represented as one format family inside a multi-format forensic architecture rather than the identity of the whole product.
- WFS detection also records observed WFS 0.4/0.5 ASCII markers while retaining structural timestamp/record evidence as the stronger signal.
- DHAV structural profiles are vendor-neutral. Vendor/model names are hints only; compatible bytes and validated structure determine family support.
- Automatic format selection now fails closed when the best result is weak or too close to another family.
- Known filesystem detection is explicitly separated from assumptions about where surveillance video is physically stored.

### Forensic behavior

- `formats list` reports the highest real capability for each active family instead of a single misleading supported/unsupported flag.
- `formats detect` ranks all active family hypotheses and exposes evidence/reasons/confidence.
- DHAV native outputs preserve complete validated frame records; chronological circular-buffer reconstruction is not implied by physical-order demultiplexing.
- Hikvision is `PROFILE` only in this milestone; HIKBTREE/data-block recording recovery is not claimed yet.
- Generic Annex-B and MPEG-PS support does not infer a recorder vendor or wall-clock timeline that the stream does not contain.

## [0.3.0-alpha] - 2026-08-21

### Added

- Bounded evidence-source profiler with reproducible sample offsets, SHA-256 sample hashes, entropy, zero/FF ratios, and known surveillance/container signature counters.
- WFS fragment-alignment hypothesis engine that ranks sector-aligned residues from structural WFS record evidence instead of claiming an unverified data offset.
- SMART/device identity snapshots using `smartctl -j`, including model, serial, firmware, capacity, sector sizes, health, temperature, power-on hours, reallocated/pending/uncorrectable indicators, and preserved raw JSON.
- CLI commands for source profiling, WFS layout hypotheses, and SMART capture.
- Regression tests for profiler sampling limits, WFS alignment ranking, SMART parsing, and profiler CLI behavior.

### Forensic behavior

- Profiling is explicitly labeled as bounded sampling rather than a complete source scan.
- A detected signature is evidence for a hypothesis, not automatic proof of a vendor/filesystem identity.
- A WFS fragment residue is explicitly kept separate from the absolute WFS data-area start.

## [0.2.0-alpha] - 2026-08-21

### Added

- Vidrensic product identity and proprietary ownership notices.
- New `vidrensic` Python package and CLI.
- Expanded forensic case model with UUID, examiner, safe case paths, and structured directories.
- Append-only SHA-256 hash-chained audit log with sequence verification and fsync.
- Persistent SQLite job/checkpoint engine using WAL and full synchronous mode.
- SHA-256/SHA-512 streaming hashing helpers.
- Linux source inspection including block-device size, sysfs read-only state, and source/child mount detection.
- Safe GNU ddrescue plan/execution model with selective offset/size acquisition, resumable map files, and resume-aware capacity checks.
- Format plugin protocol and registry.
- WFS timestamp codec, record parser, recording-boundary scanner, and detection plugin.
- Conservative WFS multi-stream reconstruction with physical-fragment mutual exclusion.
- Native HEVC extraction from reconstructed WFS packet chains with neutral candidate IDs and cryptographic hashes.
- WFS recovery manifest generation.
- Format-neutral reconstruction graph model.
- Structured ffprobe integration, fast three-point QC, and full-decode QC policy.
- Synthetic unit tests and Python 3.11/3.12/3.13 CI matrix.

### Changed

- Replaced the previous internal `Cybrex Video Forensics` / `cvf` naming with **Vidrensic**.
- The original `WFS-5.0` repository remains separate and unchanged as the stable case-work tool.

### Security

- External processes are invoked without shell interpolation.
- Write-enabled or mounted evidence block devices are rejected by default for acquisition.
- WFS packet sizes and extraction carry buffers are bounded.

## [0.1.0-alpha] - 2026-08-20

- Initial independent forensic-platform bootstrap.
