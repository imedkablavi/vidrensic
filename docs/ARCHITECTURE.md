# Vidrensic Architecture

## 1. Engineering objective

Vidrensic treats proprietary surveillance recovery as an evidence reconstruction
problem, not ordinary file undelete. The core must therefore keep acquisition,
format interpretation, reconstruction hypotheses, media validation, analyst
judgment, and exported derivatives as separate layers.

## 2. Trust boundaries

### Evidence source

The original disk/image is outside Vidrensic's mutable workspace. Block-device
sources are expected to be read-only and unmounted. The application never repairs
or mounts the source filesystem.

### Case workspace

A case is mutable working state. It contains acquisition outputs, derived native
streams, review proxies, reports, logs, and job state. Case mutation is auditable
but does not imply that every file is immutable.

### External tools

GNU ddrescue, ffprobe, and FFmpeg are external executables. Vidrensic constructs
argument arrays and never uses shell command interpolation for evidence paths.
Tool versions will be captured in a later job-manifest milestone.

## 3. Layer model

```text
CLI / future workstation
        |
        v
Case + job orchestration
        |
        +--> acquisition
        +--> plugin registry
        +--> validation/media
        +--> reporting/export
                 |
                 v
          format plugins
                 |
         +-------+-------+
         |               |
        WFS            future
         |
   parser/scanner
         |
   reconstruction
         |
 native extraction
```

The core has no WFS constants. Format-specific framing, timestamps, and fragment
rules live under `vidrensic.plugins.wfs`.

## 4. Case model

Every case receives:

- a human case ID;
- a random UUID;
- UTC creation timestamp;
- optional examiner identity;
- schema version;
- append-only audit log.

Directory layout:

```text
CASE-ID/
├── case.json
├── evidence/
├── acquisitions/
├── derived/
│   ├── native/
│   └── review/
├── work/
├── exports/
├── reports/
├── logs/
│   └── audit.jsonl
└── state/
```

`safe_path()` prevents a destructive operation from resolving outside the case
root when future cleanup/export APIs are added.

## 5. Audit integrity

Each audit event contains:

- monotonically increasing sequence;
- UTC timestamp;
- event type;
- actor;
- host and PID;
- Vidrensic version;
- structured details;
- previous-entry SHA-256;
- current-entry SHA-256.

The chain detects line modification, insertion, and reordering. Detecting complete
truncation requires preservation of an expected tail hash outside the log. A
future release will support signed case manifests and external timestamping.

## 6. Acquisition

The acquisition layer separates planning from execution.

`AcquisitionPlan` stores:

- source path;
- output path;
- ddrescue map path;
- input offset;
- acquisition size;
- retry policy;
- direct-I/O preference.

The initial pass uses ddrescue `-n` to prioritize readable data. Optional retries
are separate. Existing map files are reused for resume.

Selective acquisition is a first-class feature because a weak DVR disk should not
be forced through a full multi-terabyte scan when the relevant evidence range is
already known.

## 7. Plugin API

Every format plugin exposes:

- name/display name;
- confidence-based source detection;
- date-based recording-boundary scan.

Future plugin API versions will add:

- profiler fingerprints;
- source-layout discovery;
- reconstruction jobs;
- native metadata extraction;
- deleted/overwritten-recording discovery;
- export capabilities.

## 8. WFS plugin

The first WFS profile is based on structures observed and tested during the
separate WFS-5.0 recovery project.

Known profile evidence includes:

- 2 MiB physical recording fragments;
- `00 00 01` record synchronization;
- record types FD/FE/FC/FA/F9;
- 16-byte FD/FE headers;
- 8-byte FC/FA/F9 headers;
- packed WFS timestamp words in observed FD/FE records;
- HEVC-bearing FD/FE/FC payloads.

This is not claimed to be a universal specification for all products named WFS.
Each future vendor/layout variation should become an explicit profile.

## 9. WFS reconstruction

The current reconstruction engine advances simultaneous candidate chains together.
Before a fragment can be considered a continuation, structural rules must pass:

1. carried record completion is possible;
2. the byte immediately after a completed carried record begins another valid
   WFS record or acceptable padding;
3. the candidate fragment parses without a hard synchronization failure.

Only after those checks does physical distance affect ranking.

A fragment cannot be assigned to two camera chains in one reconstruction.
Multiple structurally valid continuations increment ambiguity evidence rather than
being hidden.

The current algorithm is a bounded local optimizer. The commercial target is a
global weighted graph solver using structural, codec, timestamp, decoder, packet
rate, neighboring-scene, and physical-distance evidence jointly.

## 10. Media layer

Native extraction and playable review media are different artifacts.

The media layer currently provides structured ffprobe output and bounded decode
windows. Planned validation includes:

- complete decode verification;
- keyframe map;
- decoder-error timeline;
- timestamp discontinuities;
- scene-sample hashes;
- frame count vs nominal timing;
- corruption-region map;
- stream-copy/remux eligibility;
- controlled proxy generation.

## 11. Review workstation target

The workstation will use a master/detail layout:

- hour/date timeline and filters;
- camera/candidate list;
- sticky preview that does not change page position;
- synchronized matrix view;
- frame stepping;
- ±1s / ±5s / ±30s controls;
- 0.25x through 8x playback;
- thumbnail/contact-sheet review;
- visible QC state;
- KEEP / REVIEW / notes / bookmarks;
- safe deletion plans limited to derived/recovered copies.

Camera slot labels are never treated as stable physical camera identity without
additional evidence.

## 12. Export model

Planned export profiles:

### Forensic master

- native recovered streams where possible;
- original timestamp metadata/sidecars;
- hashes;
- reconstruction manifest;
- audit excerpt;
- tool/version manifest.

### Review package

- broadly playable media;
- simplified filenames;
- HTML index/timeline;
- hashes and provenance link back to forensic master.

A review copy must never be mislabeled as native evidence when transcoding or
timestamp normalization occurred.
