# Roadmap

## 0.1-alpha — Forensic foundation

- case directories and metadata
- hash-chained audit log
- SHA-256/SHA-512 helpers
- Linux source inspection and read-only checks
- resumable ddrescue acquisition planning
- plugin API
- initial WFS profile
- CLI foundation
- CI and regression tests

## 0.2-alpha — WFS migration

- migrate proven WFS scanning/reconstruction logic from the stable WFS-5.0 project
- preserve the old repository unchanged
- recording boundary discovery
- WFS timestamp decoding
- packet parser and fragment continuation
- native HEVC extraction
- ffprobe/ffmpeg QC
- migration tests using synthetic fixtures

## 0.3-alpha — Graph reconstruction

- fragment candidate graph
- weighted edge evidence
- joint multi-camera path optimization
- mutual exclusion
- ambiguity/conflict explanations
- partial-overwrite salvage map

## 0.4-alpha — Forensic workstation

- case/source/date navigation
- sticky video preview
- synchronized matrix playback
- hour/camera/QC filters
- frame and second stepping
- playback speeds
- keyframe-aware seeking
- thumbnails/contact sheets
- bookmarks, notes and KEEP decisions

## 0.5-alpha — Evidence export

- forensic-master package
- review-copy package
- native vs derived labeling
- artifact hashes
- lineage manifest
- HTML technical report
- chain-of-custody report
- reproducibility bundle

## 0.6+ — Format expansion

- DVR profiler for unsupported systems
- additional filesystem/container plugins
- RAID/JBOD source abstraction
- E01/AFF4 adapters
- audio extraction
- timestamp/timezone drift analysis
- frame-level inaccessible-video salvage
- optional GPU proxy generation

## Validation gate before 1.0

A 1.0 release requires a documented validation corpus, expected-output hashes/metrics, corruption/overwrite fixtures, regression tests, reproducibility tests, versioned forensic procedures, and independent verification against known-good samples.
