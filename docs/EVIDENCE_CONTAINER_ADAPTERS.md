# E01 / Ex01 / AFF4 read-only adapter strategy

## Current release status

Vidrensic does **not** currently claim native E01, Ex01 or AFF4 support. The implemented `RandomAccessReader` layer covers ordinary read-only files/block devices, concatenation/JBOD and supplied RAID0 stripe hypotheses. Container adapters remain a release-blocked integration until their backends and fixtures pass the qualification below.

## Required adapter contract

A container backend must expose the existing read-only `RandomAccessReader` semantics:

- deterministic logical `size`;
- `read_at(offset, size)` with no implicit writes, mounting or extraction to evidence media;
- bounded reads that return at most the requested bytes;
- explicit close behavior;
- a `describe()` record containing backend/library identity, container path, logical size and read-only status;
- no mutation API in the Vidrensic adapter;
- backend exceptions translated into explicit read/verification failures, never fabricated zero-filled data unless the container format itself proves that range is logically sparse and the report records that fact.

## Backend candidates

### E01 / Ex01

A practical Python implementation would normally wrap a maintained libewf binding. Qualification must verify segmented-image ordering, missing-segment failure, stored metadata, chunk checksum behavior, random seek correctness and large-offset reads. The adapter must never silently continue when a segment is missing or a backend checksum fails.

### AFF4

AFF4 support should wrap a maintained AFF4 implementation rather than reimplementing the container format in Vidrensic. Qualification must cover logical streams, sparse ranges, resolver metadata, compression, container hashes where available and explicit failure when referenced objects are missing.

## Fail-closed rules

1. Unknown or unsupported container variant: stop with `UNKNOWN`/error; do not fall back to treating the container bytes as a raw disk image.
2. Missing EWF segment or AFF4 object: stop the logical reader; do not synthesize continuity.
3. Container-level checksum failure: surface integrity failure before parser/reconstruction claims.
4. Backend not installed: report adapter unavailable; do not weaken verification.
5. Logical size mismatch across independent probes: block reconstruction pending review.

## Qualification fixtures

Before enabling a backend in release builds, add legally redistributable fixtures covering:

- single-segment and multi-segment E01/Ex01;
- deliberately missing/corrupted EWF segment;
- AFF4 logical image with compression;
- AFF4 sparse range;
- malformed/truncated container headers;
- known byte windows at start, middle and end with independently computed SHA-256;
- random-read equivalence against a separately exported raw image.

The raw export is a validation oracle for byte equivalence only. It does not prove that Vidrensic created a forensically valid acquisition.

## Packaging decision

Keep container libraries optional until qualification is complete. A recommended future packaging shape is an extra such as `vidrensic[ewf]` / `vidrensic[aff4]`, avoiding mandatory heavy native dependencies for users who only analyze raw images. Binary/native dependency provenance must be captured in release qualification.

## Promotion gate

Do not add E01/Ex01/AFF4 to the public support matrix as `PARSE`/`RECONSTRUCT` until CI has the fixture matrix above and at least one release artifact has been installed in a clean environment with the optional backend enabled. Until then, this document is a strategy, not a support claim.
