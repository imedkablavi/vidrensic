# Vidrensic Validation and QA

Vidrensic separates **software capability** from **forensic validation**. Passing CI proves a defined automated test set passed for a commit; it does not prove every recorder variant is supported or independently certify the software for evidentiary use.

## Automated release gates

Pull requests and `main` are tested across Python 3.11, 3.12 and 3.13 on Linux. The CI pipeline checks:

- dependency consistency with `pip check`;
- Ruff static/lint checks;
- Python bytecode compilation;
- unit and synthetic regression tests;
- malformed-input/parser safety cases;
- concurrency regressions for audit/job state;
- crypto known-answer and receipt behavior;
- acquisition map/receipt behavior;
- source/provenance/time models;
- WFS/DHAV/Hikvision/profile regressions;
- global reconstruction solver cases;
- total coverage gate of at least 70%;
- source distribution and wheel build;
- fresh install of the built wheel;
- CLI/import smoke tests against the installed wheel.

The GitHub Actions run is the authoritative current result.

## Validation layers

### 1. Unit correctness

Pure functions, parsers, record models and deterministic transforms are tested against compact known inputs.

### 2. Adversarial / malformed inputs

Parsers receive short, truncated, inconsistent and randomized byte sequences. The expected outcome is bounded rejection or explicit uncertainty — never uncontrolled reads or plausible fabricated metadata.

### 3. Synthetic reconstruction

Synthetic layouts exercise fragmentation, competing paths, codec evidence, continuity and ambiguity behavior with known expected answers.

### 4. Packaging/runtime

The built wheel is installed into CI and smoke-tested so editable-source success cannot hide packaging failures.

### 5. Recorder-family validation

This layer requires versioned real or legally distributable fixtures from known recorder/firmware variants. It is intentionally tracked separately from generic parser tests.

## Status semantics

- `PASS`: required validation ran and no unresolved hard condition remains.
- `REVIEW`: useful output exists but ambiguity or incomplete evidence remains.
- `FAIL`: strong structural/decoding/integrity inconsistency exists.
- `UNKNOWN`: required validation did not run.

Successful parsing alone should not create `PASS`.

## Evidence-source safety tests

Block-device operations are designed around read-only access. Any workflow that intentionally permits a write-enabled source must make that override explicit and auditable. Tests should never depend on repairing or mounting evidence read-write.

## Cryptography validation

Current crypto support is a known-key primitive layer. Tests use known-answer AES vectors and verify that key material is represented by fingerprints rather than written into receipts/logs. Vendor-specific key derivation must be validated separately per profile.

## Before a stable forensic release

A stable release should additionally have:

- a published versioned validation corpus manifest;
- known-good and intentionally corrupted examples for every claimed recovery family;
- repeatability results across clean environments;
- interruption/resume and low-space acquisition tests;
- large-source performance/memory benchmarks;
- signed release artifacts and SBOM/dependency review;
- documented limitations per recorder/firmware profile;
- independent or organization-specific validation where required.

See also `docs/FORENSIC_POLICY.md` and `docs/SUPPORT_MATRIX.md`.
