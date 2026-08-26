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
- acquisition command/preflight/map/receipt behavior;
- source/provenance/time models;
- WFS/DHAV/Hikvision/profile regressions;
- path-dependent and generic global reconstruction solver cases;
- total line coverage gate of at least **80%**;
- separate minimum coverage thresholds for forensic-critical modules;
- public validation-corpus execution from the editable build;
- source distribution and wheel build;
- fresh install of the built wheel;
- public validation-corpus execution from the installed wheel;
- CLI/import smoke tests against the installed wheel.

The GitHub Actions run is the authoritative current result.

### Critical-module coverage gates

The total percentage is not allowed to hide a weak parser or evidence-handling module. CI independently enforces minimum coverage for selected critical modules. Current gates include:

| Module | Minimum |
|---|---:|
| WFS local reconstruction | 80% |
| WFS path-dependent global reconstruction | 85% |
| WFS high-level recovery | 85% |
| Generic recovery solver | 90% |
| Hashing | 90% |
| Provenance | 90% |
| Known-key crypto transforms | 80% |
| ddrescue acquisition orchestration | 75% |

Thresholds are floors, not targets. They should rise as meaningful failure-path tests are added.

## Validation layers

### 1. Unit correctness

Pure functions, parsers, record models and deterministic transforms are tested against compact known inputs.

### 2. Adversarial / malformed inputs

Parsers receive short, truncated, inconsistent and randomized byte sequences. The expected outcome is bounded rejection or explicit uncertainty - never uncontrolled reads or plausible fabricated metadata.

### 3. Synthetic reconstruction

Synthetic layouts exercise fragmentation, competing paths, codec evidence, continuity and ambiguity behavior with known expected answers.

For WFS this includes path-dependent carry/tail hypotheses, cross-camera fragment competition, second-best solution evidence and bounded-search truncation.

### 4. Validation corpus

The versioned corpus runner treats ground truth as data rather than test-code assumptions. Each case can declare:

- provenance and redistributability;
- exact source SHA-256;
- expected operations and results;
- expected-vs-actual output in a machine-readable report.

The loader rejects path traversal and symlink sources and fails a source-hash mismatch before recovery operations run.

The public corpus is deliberately synthetic. Passing it validates corpus mechanics and declared synthetic expectations; it does **not** establish broad real-recorder compatibility.

See `docs/VALIDATION_CORPUS.md`.

### 5. Packaging/runtime

The built wheel is installed into CI and smoke-tested so editable-source success cannot hide packaging failures. The validation corpus is rerun against the installed wheel.

### 6. Recorder-family validation

This layer requires versioned real or legally distributable fixtures from known recorder/firmware variants. It is intentionally tracked separately from generic parser tests.

For each real fixture, ground truth should document acquisition controls, source hashes, recorder/firmware identity, known recording intervals, injected/observed corruption, expected recovered structures and timestamp tolerances.

### 7. Independent rerun

A family should not be promoted to independently validated maturity merely because the developers can reproduce their own fixture result. A separate examiner/lab should be able to execute the declared corpus/report procedure from hashes and instructions without developer intervention.

## Status semantics

- `PASS`: required validation actually ran and no unresolved hard condition remains.
- `REVIEW`: useful output exists but ambiguity or incomplete evidence remains.
- `FAIL`: strong structural/decoding/integrity inconsistency exists.
- `UNKNOWN`: required validation did not run.

Successful parsing or native extraction alone should not create `PASS`.

A WFS global search that reaches its configured hypothesis/combination bound is explicit `REVIEW` evidence; it is never represented as a proven optimum.

## Evidence-source safety tests

Block-device operations are designed around read-only access. Any workflow that intentionally permits a write-enabled source must make that override explicit and auditable. Tests should never depend on repairing or mounting evidence read-write.

## Cryptography validation

Current crypto support is a known-key primitive layer. Tests use known-answer AES vectors and verify that key material is represented by fingerprints rather than written into receipts/logs. Vendor-specific key derivation must be validated separately per profile.

## Current limitations of validation claims

The project is still alpha. In particular:

- the public corpus does not yet contain a broad multi-vendor set of real recorder images;
- WFS global reconstruction is structurally and synthetically tested but still needs broad firmware/device validation;
- WFS frame/GOP-level partially overwritten salvage is not complete;
- Hikvision support remains profiling-level rather than reconstruction-level;
- DHAV circular chronology/audio/variant coverage is incomplete;
- there is no published independent lab validation report yet.

## Before a stable forensic release

A stable release should additionally have:

- a larger published versioned validation corpus manifest;
- known-good and intentionally corrupted examples for every claimed recovery family;
- repeatability results across clean environments;
- interruption/resume and low-space acquisition tests;
- large-source performance/memory benchmarks;
- signed release artifacts and SBOM/dependency review;
- documented limitations per recorder/firmware profile;
- independent or organization-specific validation where required.

See also `docs/FORENSIC_POLICY.md`, `docs/VALIDATION_CORPUS.md` and `docs/SUPPORT_MATRIX.md`.
