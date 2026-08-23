# Acquisition / hash / provenance failure recovery

This procedure describes recovery from interrupted or failed acquisition operations. It is not a claim that a damaged source was fully acquired.

## Existing guarantees

Vidrensic uses GNU ddrescue map files for resumable acquisition, checks source safety immediately before execution, verifies requested geometry, and writes acquisition receipts atomically through a temporary `.partial` path. Source fingerprints can bind a resume decision to path/device identity, geometry, metadata and optional edge samples.

## Required resume procedure

1. Preserve the existing ddrescue map and partial output. Do not delete or rewrite them merely to make the next run look clean.
2. Reinspect the evidence source. If a previously recorded `SourceFingerprint` exists, compare it with the current fingerprint before resuming.
3. If source identity changed, stop. Do not resume against a different disk/image even when its size is identical.
4. Re-run destination-capacity checks using the current partial-output size.
5. Resume using the same map file and explicit acquisition geometry.
6. After ddrescue returns, parse the map against the requested range. Any unresolved/non-finished range keeps the result in review.
7. Hash the resulting image and map unless an explicit policy says otherwise. A skipped or failed output hash does not establish a complete verified acquisition.
8. Write a new receipt only after all available state has been evaluated. A receipt serialization failure must not leave a final success-looking JSON file.

## Failure classes

### Source identity mismatch

**Action:** fail closed. Preserve the old map/output and investigate why the source changed. Do not silently bind the old map to the new source.

### ddrescue non-zero return

**Action:** preserve map/output, record the return code, inspect map state and decide whether a controlled resume is appropriate. A non-zero pass is not converted to `COMPLETE` merely because output bytes exist.

### Unresolved map ranges

**Action:** status remains review/incomplete. Bad-sector, non-tried, non-trimmed and non-scraped ranges must remain visible.

### Output shorter than requested geometry

**Action:** review/failure condition. Do not pad it and call the acquisition complete unless a separate container format explicitly defines sparse ranges and that behavior is recorded.

### Hash skipped or hash operation failure

**Action:** verification is incomplete. Keep the bytes, record the reason, and retry hashing from the preserved output when operationally safe. Never invent a digest or reuse one from a different file.

### Receipt write failure

**Action:** no final receipt should exist. Preserve acquisition bytes/map, correct the destination failure and rerun receipt generation. An old `.partial` receipt blocks overwrite so an examiner must inspect it deliberately.

## Known gap

The source-fingerprint comparison primitive exists, but the current ddrescue CLI resume path does not yet persist and automatically require a prior fingerprint sidecar on every resume. Until that binding is integrated and validated, operators must treat source-identity comparison as an explicit workflow requirement rather than an automatic guarantee.

This gap is a release-readiness limitation, not something hidden by a passing unit test.
