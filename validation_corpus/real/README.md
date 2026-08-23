# Real-recorder validation corpus

This directory is the admission gate for **real or legally redistributable recorder fixtures**. It intentionally contains no recorder image today. Synthetic data must not be relabelled as real validation.

## Required before a fixture is admitted

Every real-recorder case must have a versioned manifest entry with all of the following:

- immutable `case_id` and `fixture_version`;
- recorder manufacturer, model and firmware/build identity, using `unknown` only when that fact is genuinely unavailable;
- acquisition method and acquisition date;
- source SHA-256 before any Vidrensic operation runs;
- provenance classification: `public`, `lab`, or `restricted`;
- legal basis describing ownership/authorization and whether redistribution is permitted;
- ground-truth method independent of Vidrensic, including known recording intervals and any intentionally introduced corruption;
- expected parser/recovery/QC results with tolerances where timestamps, frame counts or byte ranges cannot be exact;
- reviewer identity or lab role for the ground truth;
- an explicit statement that the fixture contains no unrelated private footage or other data that cannot lawfully be retained/distributed.

`real-corpus-index.json` is the versioned machine-readable index. A zero-case index is valid and means **no real-recorder validation claim is available**.

## Legal/data handling

Do not commit customer evidence, seized evidence, credentials, unrelated private video, or a recorder image merely because it is technically useful. Restricted fixtures should normally remain outside the public repository; the index may record their hashes/metadata without publishing bytes only when policy and authorization allow it.

## Promotion rule

A family-specific parser may be developed with synthetic fixtures, but recorder-family validation claims require admitted real cases. Hikvision remains profiling-only until real fixtures cover the exact layouts being parsed. WFS/DHAV reconstruction capability and real-recorder validation are separate claims.

## PASS semantics

A case `PASS` means only that the declared expectations for the exact hashed fixture, manifest version and Vidrensic commit were satisfied. It does not prove universal vendor/firmware support, evidentiary admissibility, absence of false negatives, or independent laboratory certification.
