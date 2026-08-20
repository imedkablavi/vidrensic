# CVF Architecture

## Trust boundaries

CVF separates the evidence source, forensic acquisition, reconstruction workspace, derived media, analyst state, and exports. No component may silently promote a derived artifact to native evidence.

## Core layers

1. **Evidence source**: read-only block device, RAW/DD image, or later E01/AFF4 source.
2. **Acquisition**: source inspection, SMART snapshot, hashing, ddrescue planning/execution, resumable maps.
3. **Case core**: case metadata, jobs, audit events, hashes, artifact lineage.
4. **Profiler/plugins**: proprietary DVR/NVR format detection and format-specific parsing.
5. **Reconstruction**: recording boundaries, fragment graph, candidate paths, ambiguity tracking, mutual exclusion.
6. **Media**: native stream extraction, timestamp sidecars, ffprobe/ffmpeg verification, corruption/keyframe maps.
7. **Review**: synchronized multi-camera review, bookmarks, notes, KEEP decisions, explicit analyst overrides.
8. **Export**: forensic masters, review copies, manifests, hashes, reports, and reproducibility metadata.

## Evidence lineage

Every artifact should be able to answer:

- which source bytes produced it;
- which plugin/profile version interpreted those bytes;
- which reconstruction decisions were automatic vs analyst-selected;
- which transformations were applied;
- which tool versions were used;
- source and output hashes;
- whether the artifact is native, reconstructed, remuxed, transcoded, or annotated.

## Recovery confidence

A candidate is never accepted based on duration alone. Confidence combines structural packet continuity, mutually exclusive fragment assignment, timestamp evidence, codec/NAL compatibility, decoder continuity, packet-rate consistency, physical locality, and optional visual continuity.

The eventual graph solver will optimize camera paths jointly so a physical fragment cannot be reused by multiple reconstructed streams without an explicit conflict result.

## Safety defaults

- source block devices must be confirmed read-only before acquisition/recovery;
- shell commands are built as argument vectors, never shell strings;
- destructive cleanup is outside evidence-source code paths;
- ambiguity defaults to REVIEW;
- audit logs are append-only and hash chained;
- derived review proxies are stored separately from native/reconstructed masters.
