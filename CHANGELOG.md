# Changelog

All notable Vidrensic development changes are recorded here.

## [0.2.0-alpha] - 2026-08-21

### Added

- Vidrensic product identity and proprietary ownership notices.
- New `vidrensic` Python package and CLI.
- Expanded forensic case model with UUID, examiner, safe case paths, and structured directories.
- Append-only SHA-256 hash-chained audit log with sequence verification and fsync.
- SHA-256/SHA-512 streaming hashing helpers.
- Linux source inspection including block-device size, sysfs read-only state, and mount detection.
- Safe GNU ddrescue plan/execution model with selective offset/size acquisition and resumable map files.
- Format plugin protocol and registry.
- WFS timestamp codec, record parser, recording-boundary scanner, and detection plugin.
- Conservative WFS multi-stream reconstruction with physical-fragment mutual exclusion.
- Native HEVC extraction from reconstructed WFS packet chains.
- Format-neutral reconstruction graph model.
- Structured ffprobe integration and bounded FFmpeg decode-window checking.
- Synthetic unit tests and CI matrix.

### Changed

- Replaced the previous internal `Cybrex Video Forensics` / `cvf` naming with **Vidrensic**.
- The original `WFS-5.0` repository remains separate and unchanged as the stable case-work tool.

### Security

- External processes are invoked without shell interpolation.
- Write-enabled or mounted evidence block devices are rejected by default for acquisition.
- WFS packet sizes and extraction carry buffers are bounded.

## [0.1.0-alpha] - 2026-08-20

- Initial independent forensic-platform bootstrap.
