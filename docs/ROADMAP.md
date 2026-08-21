# Vidrensic Engineering Roadmap

This roadmap is ordered by forensic dependency, not by visual appeal. A feature is not considered production-ready until it has regression fixtures, bounded failure behavior and validation evidence matching the claim.

## Phase A — Forensic foundation ✅

- [x] Independent repository and product identity
- [x] Proprietary ownership/license notices
- [x] Case directory and schema
- [x] Hash-chained audit log
- [x] SHA-256/SHA-512 hashing
- [x] Linux block-source inspection
- [x] Read-only/mount safety checks
- [x] Selective/full ddrescue planning and execution
- [x] ddrescue map parsing and acquisition receipts
- [x] source identity/provenance models
- [x] plugin protocol/registry
- [x] CI + Security automation

## Phase B — WFS reconstruction 🧪

- [x] WFS timestamp codec
- [x] WFS record framing parser
- [x] date/hour start-boundary scanner
- [x] conservative local multi-stream reconstruction
- [x] codec-neutral H.264/H.265/ES native extraction
- [x] reconstruction manifest with ambiguity/unresolved evidence
- [x] path-dependent carry/tail hypothesis enumeration
- [x] global physical-fragment-disjoint selection
- [x] second-best / bounded-search ambiguity evidence
- [x] regression for physical-fragment-boundary continuation probing
- [ ] absolute data-base-offset discovery with corroborating metadata evidence
- [ ] recording-boundary successor/time model
- [ ] packet-rate and timestamp continuity evidence integrated into global path cost
- [ ] decoder/keyframe evidence integrated into reconstruction confidence
- [ ] real multi-recorder/firmware validation corpus
- [ ] frame/NAL/GOP-level partial-overwrite salvage

Exit criteria for higher maturity:

- known real WFS fixtures are reproducible from hashes and declared geometry;
- local/global differences are explainable from recorded evidence;
- no physical fragment is silently reused across simultaneous selected chains;
- bounded/truncated global searches remain REVIEW rather than fake optimum/PASS;
- partially overwritten cases produce explicit salvage/corruption maps.

## Phase C — Evidence acquisition workstation

- [x] case-aware acquisition jobs
- [x] source identity capture foundation
- [x] SMART snapshot support
- [x] GNU ddrescue planning/map/resume
- [x] free-space preflight and FAT32 single-file checks
- [x] acquisition receipt and hashes
- [ ] acquisition progress API/UI
- [ ] safe automatic image splitting where the target filesystem requires it
- [ ] interruption/kill/resume stress corpus
- [ ] bad-sector simulator and repeatable acquisition failure tests

## Phase D — Global reconstruction solver 🧪

### Generic solver

- [x] node-disjoint path foundation
- [x] global competing-start optimization
- [x] alternative-solution margin
- [x] deterministic regression fixtures

### WFS-specific path-dependent solver

- [x] preserve branch-specific carry/tail state
- [x] bounded beam hypothesis enumeration
- [x] global disjoint hypothesis selection across simultaneous starts
- [x] explicit combination search cap and truncation flag
- [ ] branch-and-bound upper/lower pruning for large candidate sets
- [ ] adaptive beam budgets based on evidence quality
- [ ] packet/NAL/timestamp/decoder continuity scoring
- [ ] performance and memory benchmarks on multi-terabyte cases
- [ ] independent real-recorder validation

Hard constraints:

- one physical fragment cannot belong to two selected simultaneous streams;
- hard-invalid structural continuations are never rescued by a soft score;
- path-dependent WFS state is never collapsed into a false context-free edge;
- search bounds and uncertainty are written into the manifest.

## Phase E — Validation corpus and QA 🧪

- [x] versioned machine-readable corpus schema
- [x] provenance + redistributability metadata
- [x] source SHA-256 ground truth
- [x] expected-vs-actual report
- [x] `source_hash`, `format_detect`, `wfs_recover` expectation types
- [x] path traversal and symlink rejection
- [x] editable-build corpus smoke
- [x] installed-wheel corpus smoke
- [x] overall coverage floor raised from 70% to 80%
- [x] separate critical-module coverage gates
- [ ] public/legal real recorder fixtures
- [ ] intentionally corrupted real/synthetic recorder corpus
- [ ] performance/memory qualification corpus
- [ ] independent rerun report from a separate examiner/lab

See `VALIDATION.md` and `VALIDATION_CORPUS.md`.

## Phase F — Media validation engine

- [ ] native stream inventory persistence
- [x] ffprobe probing foundation
- [x] fast/full decode QC foundations
- [ ] keyframe index
- [ ] PTS/DTS anomaly map
- [ ] decoder error regions
- [ ] frame-rate inference with confidence
- [ ] duration confidence separate from nominal duration
- [ ] visual scene sampling/contact sheets
- [ ] duplicate/near-duplicate detection
- [ ] remux-first repair workflow
- [ ] controlled transcode proxy workflow

## Phase G — Review workstation

Primary review UX target:

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

- [ ] sticky preview
- [ ] hour/date/candidate filters
- [ ] synchronized matrix view
- [ ] thumbnail/contact-sheet strip
- [ ] frame stepping and playback-speed controls
- [ ] seek watchdog/reload-position recovery
- [ ] bookmarks and analyst notes
- [ ] KEEP/review state
- [ ] safe derived-copy deletion plans bound to file identity
- [ ] deletion audit/tombstones

## Phase H — Unknown DVR/NVR profiler

- [x] bounded source samples
- [x] entropy/signature evidence
- [x] storage/partition profiling
- [x] physical signature hit maps
- [x] ranked format-family detection
- [x] WFS fragment-alignment hypotheses
- [ ] absolute proprietary data-area discovery with corroborating evidence
- [ ] anonymized profiler bundle format
- [ ] profile/plugin SDK documentation

The profiler must never silently upload evidence.

## Phase I — Additional recorder families

- [ ] Hikvision HIKBTREE/data-block variants
- [ ] WFH 1/2/3/4
- [ ] IFS family variants
- [ ] Stream / Stream_db
- [ ] TangoMagic
- [ ] additional DHFS/DHAV variants
- [ ] TDFS/BJPEG/JDAT/Milefs and other field-observed families

No family is promoted from a research target merely because its name or signature is known.

## Phase J — Deleted and partially overwritten recovery

- [ ] orphan recording-start discovery
- [ ] unindexed fragment sets
- [ ] stale metadata classification
- [ ] overwritten-chain evidence
- [ ] frame/NAL-level salvage mode
- [ ] partial GOP recovery
- [ ] corruption intervals in exported report
- [ ] confidence separated from playable duration

## Phase K — Multi-disk and forensic image formats

- [x] file/JBOD/RAID0 random-access foundation with supplied geometry
- [ ] RAID0 geometry discovery/validation
- [ ] RAID5/6 parity reconstruction
- [ ] E01/Ex01 adapter with independent verification
- [ ] AFF4 adapter with independent verification
- [ ] multi-disk recorder profile hypotheses

## Phase L — Evidence export & reporting

- [ ] forensic-master export profile
- [ ] review-copy export profile
- [ ] hashes for every exported artifact
- [ ] provenance graph
- [ ] signed manifest option
- [ ] HTML/PDF technical reports
- [ ] chain-of-custody summary
- [ ] examiner notes/bookmarks export
- [ ] external review index

## Phase M — Commercial hardening

- [ ] structured logging and schema migrations
- [ ] crash-safe transaction review
- [ ] deeper fuzz/property testing for proprietary parsers
- [ ] performance and file-descriptor stress tests
- [ ] packaged Linux application/workstation
- [ ] signed release artifacts
- [ ] reproducible build documentation
- [ ] SBOM generation
- [ ] dependency/license inventory
- [ ] security threat model
- [ ] validation handbook and operator SOP
- [ ] plugin developer SDK

## Validation gates

A feature may move to `PASS`-capable or `VALIDATE` maturity only when the scope of the claim has matching evidence:

1. known-good fixtures pass;
2. intentionally corrupted fixtures produce expected REVIEW/FAIL behavior;
3. failure does not modify evidence;
4. parameters required to reproduce output are recorded;
5. derived timestamps/media are distinguishable from native evidence;
6. source/fixture hashes are recorded;
7. documented limitations match actual behavior;
8. real-device claims are backed by real-device fixtures for declared variants;
9. independent rerun evidence exists where independent validation is claimed.
