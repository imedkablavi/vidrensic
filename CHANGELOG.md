# Changelog

All notable Vidrensic development changes are recorded here.

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
