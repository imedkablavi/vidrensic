# Vidrensic Engineering Roadmap

This roadmap is ordered by forensic dependency, not by visual appeal. A feature is
not considered production-ready until it has regression fixtures and documented
failure behavior.

## Phase A — Forensic foundation ✅ / active

- [x] Independent repository and product identity
- [x] Proprietary ownership/license notices
- [x] Case directory and schema
- [x] Hash-chained audit log
- [x] SHA-256/SHA-512 hashing
- [x] Linux block-source inspection
- [x] Read-only/mount safety checks
- [x] Selective ddrescue planning and execution
- [x] Plugin protocol/registry
- [x] CI and synthetic unit-test foundation

Exit criteria:

- case/audit tamper tests pass;
- unsafe acquisition states are rejected;
- CLI behavior is deterministic across supported Python versions.

## Phase B — WFS plugin migration 🧪

- [x] WFS timestamp codec
- [x] WFS record framing parser
- [x] Date/hour start-boundary scanner
- [x] Conservative multi-stream fragment reconstruction
- [x] Native HEVC packet extraction
- [ ] Data-base-offset discovery/profile detection
- [ ] Recording-boundary successor model
- [ ] Exact expected-duration calculation from neighboring timestamps
- [ ] Packet-rate QC migration
- [ ] scene discontinuity QC migration
- [ ] full decode QC migration
- [ ] reconstruction manifest schema
- [ ] known-good Day 7/Day 8 regression manifests

Exit criteria:

- WFS-5.0 known recovery cases can be reproduced without changing source output
  semantics;
- every ambiguity currently visible in WFS-5.0 remains visible or gains stronger
  evidence;
- no physical fragment is silently reused between simultaneous camera chains.

## Phase C — Evidence acquisition workstation

- [ ] `vidrensic acquire` case-aware job object
- [ ] capture source identity: model, serial, firmware, geometry
- [ ] SMART snapshot import
- [ ] GNU ddrescue version capture
- [ ] free-space preflight with sparse-image awareness
- [ ] resume/restart checkpoint database
- [ ] acquisition progress API
- [ ] bad/unreadable range summary
- [ ] whole-device and selective-range acquisition profiles
- [ ] source + acquisition hash manifests
- [ ] safe image splitting for target filesystem limits

## Phase D — Global reconstruction solver

Replace the bounded WFS local assignment with a weighted graph model.

Candidate edge evidence:

- exact carried-record completion;
- valid record at join boundary;
- packet/NAL validity;
- SPS/PPS/VPS compatibility;
- proprietary timestamp continuity;
- packet-rate continuity;
- decoder continuity;
- physical gap;
- neighboring segment continuity;
- optional visual fingerprint similarity.

Constraints:

- one physical fragment cannot belong to two simultaneous recovered streams;
- hard-invalid structural edges are never rescued by a soft score;
- solver uncertainty must be reported, not collapsed into a fake PASS.

## Phase E — Media validation engine

- [ ] native stream inventory
- [ ] ffprobe schema persistence
- [ ] full decode worker
- [ ] three-point fast validation
- [ ] keyframe index
- [ ] PTS/DTS anomaly map
- [ ] decoder error regions
- [ ] frame-rate inference with confidence
- [ ] duration confidence separate from nominal duration
- [ ] visual scene sampling/contact sheets
- [ ] duplicate/near-duplicate detection
- [ ] remux-first repair workflow
- [ ] controlled transcode proxy workflow

## Phase F — Review workstation

Primary review UX:

```text
┌───────────────────────────────────────────────────────────┐
│ Case / Source / Date / Search / QC filters                │
├────────────────────────────┬──────────────────────────────┤
│ Hours + candidates         │ Sticky player               │
│                            │                              │
│ 09:00  4 candidates        │ frame / ±1 / ±5 / ±30       │
│ 10:00  4 candidates        │ .25x .5x 1x 2x 5x 8x        │
│ 11:00  REVIEW              │ fullscreen retains controls │
│                            ├──────────────────────────────┤
│ KEEP / notes / bookmarks   │ QC / timeline / metadata    │
├────────────────────────────┴──────────────────────────────┤
│ thumbnails / synced multi-camera timeline                │
└───────────────────────────────────────────────────────────┘
```

- [ ] sticky preview with no page jump
- [ ] hour/date filters
- [ ] camera/candidate filters
- [ ] synchronized matrix view
- [ ] thumbnail strip/contact sheet
- [ ] frame stepping
- [ ] playback-speed controls
- [ ] seek watchdog/reload-position recovery
- [ ] bookmarks and analyst notes
- [ ] KEEP semantics
- [ ] reviewed-hour state
- [ ] safe derived-copy deletion plan
- [ ] plan ID bound to file identity and selection state
- [ ] deletion audit/tombstones

## Phase G — Unknown DVR/NVR profiler

A profiler should collect a small, privacy-conscious technical sample for formats
that lack a plugin.

- [ ] disk geometry/layout summary
- [ ] entropy and repeating-block map
- [ ] filesystem/signature candidates
- [ ] video start-code/codec signatures
- [ ] timestamp-pattern candidates
- [ ] fragment-size hypotheses
- [ ] sample extraction with explicit byte ranges
- [ ] anonymized profiler bundle
- [ ] profile SDK documentation

The profiler must never silently upload evidence.

## Phase H — Deleted and partially overwritten recovery

- [ ] orphan recording-start discovery
- [ ] unindexed fragment sets
- [ ] stale metadata classification
- [ ] overwritten-chain evidence
- [ ] frame/NAL-level salvage mode
- [ ] partial GOP recovery
- [ ] corruption intervals in exported report
- [ ] confidence score separated from playable duration

## Phase I — Evidence export & reporting

- [ ] forensic-master export profile
- [ ] review-copy export profile
- [ ] hashes for every exported artifact
- [ ] provenance graph
- [ ] signed manifest option
- [ ] HTML report
- [ ] PDF report
- [ ] chain-of-custody summary
- [ ] examiner notes/bookmarks export
- [ ] external review index
- [ ] FAT32/exFAT/NTFS target capability checks

## Phase J — Commercial hardening

- [ ] structured logging
- [ ] SQLite job/state schema with migrations
- [ ] crash-safe transactions
- [ ] fuzz testing for proprietary parsers
- [ ] synthetic corruption corpus
- [ ] performance benchmarks
- [ ] memory and file-descriptor stress tests
- [ ] packaged Linux releases
- [ ] signed release artifacts
- [ ] reproducible build documentation
- [ ] SBOM generation
- [ ] dependency/license inventory
- [ ] security threat model
- [ ] validation handbook
- [ ] operator SOP
- [ ] plugin developer SDK

## Validation gates

A feature may move to `PASS-capable` only when:

1. known-good fixtures pass;
2. intentionally corrupted fixtures produce the expected REVIEW/FAIL result;
3. failure does not modify evidence;
4. parameters required to reproduce the output are recorded;
5. derived timestamps/media are distinguishable from native evidence;
6. documented limitations match actual behavior.
