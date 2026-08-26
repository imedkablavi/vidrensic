# Forensic Operating Policy

This document defines software behavior targets. It is not a substitute for an
agency's legal, evidentiary, accreditation, or chain-of-custody procedures.

## Evidence preservation

- Prefer a hardware/software write blocker or a confirmed Linux read-only block
  device.
- Never run filesystem repair against the evidence source.
- Never mount proprietary evidence filesystems through Vidrensic.
- Acquire a clone/image first when source health or case procedure requires it.
- Preserve ddrescue map files because they describe unreadable/retried ranges and
  make acquisition resumable.

## Source identity

Future case manifests should capture, where available:

- device model;
- serial number;
- firmware revision;
- capacity and logical/physical sector sizes;
- interface path;
- SMART snapshot;
- source read-only status;
- acquisition tool/version;
- source/acquisition hashes.

## Native vs derived evidence

Vidrensic uses these categories:

**Source** - original evidence device/image.

**Acquisition** - forensic clone or bounded byte-range image.

**Native recovered artifact** - payload extracted/reconstructed without
intentional media transcoding.

**Derived review artifact** - remuxed, normalized, transcoded, enhanced, clipped,
or otherwise transformed media intended for review convenience.

Every derived artifact should retain provenance to its input artifacts and the
parameters/tool versions used to create it.

## Timestamp policy

- Preserve observed recorder timestamps exactly in metadata.
- Do not overwrite native time with analyst-corrected time.
- Store timezone/correction/drift as separate transformations.
- Label interpolated or inferred times as derived.
- Preserve discontinuities and clock jumps as evidence rather than automatically
  smoothing them away.

## Recovery decisions

`PASS` requires all mandatory validation for the profile and no unresolved hard
or ambiguous condition.

`REVIEW` means a candidate may be useful but cannot receive an automatic forensic
PASS. Examples include incomplete validation, multiple plausible fragment joins,
small timing anomalies, scene discontinuities, or partially unreadable evidence.

`FAIL` indicates a strong structural/media/timing inconsistency.

`UNKNOWN` means the required validation has not run.

Playable media is not equivalent to forensic correctness.

## Destructive actions

Any future deletion/cleanup feature must:

- operate only on explicitly derived/recovered-copy roots;
- never delete source evidence, acquisition images, map files, audit logs, or
  manifests through ordinary review cleanup;
- use KEEP semantics rather than ambiguous "select for delete" semantics;
- preview a deletion plan before execution;
- bind the plan to file identity and analyst selections;
- reject stale plans after files/selections change;
- record tombstones and audit events.

## External tool behavior

External commands are argument arrays, not shell strings. File paths and metadata
must never be interpolated into a shell command.

Decoder/converter warnings are evidence for QC, not text to hide. A command
returning success does not automatically make a recording PASS.

## Validation corpus

Commercial/evidentiary releases should maintain:

- known-good source images;
- known expected recording boundaries;
- missing-fragment fixtures;
- overwritten-fragment fixtures;
- corrupt packet-length fixtures;
- timestamp jump fixtures;
- camera-slot permutation fixtures;
- identical-codec multi-camera fixtures;
- decoder corruption fixtures;
- target-filesystem size-limit fixtures.

Expected output manifests should be version controlled independently from customer
case evidence.
