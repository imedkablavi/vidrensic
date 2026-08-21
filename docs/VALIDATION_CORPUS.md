# Validation corpus

Vidrensic treats validation data as evidence about the tool, not as marketing material.

A green unit-test suite proves that code behaves as the tests describe. A forensic validation corpus answers a different question: **does a declared build reproduce known ground truth on known recorder data under documented conditions?**

## Corpus case requirements

Every case must declare:

- a unique `case_id`;
- a source path relative to the corpus manifest;
- format/family label;
- provenance classification: `synthetic`, `public`, `lab`, or `restricted`;
- whether the fixture is redistributable;
- an expected SHA-256 when ground-truth bytes are fixed;
- one or more deterministic expectations;
- notes describing important limitations.

The loader rejects absolute source paths, traversal outside the manifest directory, duplicate case IDs, malformed hashes and missing files. A declared source SHA-256 mismatch fails the case before recovery/detection expectations run.

## Supported expectation kinds

### `source_hash`

Verifies the exact source bytes. This is useful for corpus integrity and release qualification.

### `format_detect`

Runs ranked format-family detection. Ground truth can assert fields such as `top_plugin`, `requires_review` and result count. Confidence values should only be pinned when a detector score is itself part of the validation target; otherwise avoid brittle score assertions.

### `wfs_recover`

Runs WFS recovery in a temporary directory. The manifest can specify starts, stop fragment, data/fragment geometry and global-search bounds. Ground truth can assert candidate count, selected fragment chains, statuses, codecs and whether the global search was truncated.

The corpus runner deletes temporary recovery products after each expectation. It records results, not evidence payload bytes.

## Running a corpus

```bash
vidrensic validate corpus validation_corpus/corpus.json \
  --out validation-report.json
```

Exit status is zero only if every case and expectation passes.

The report records:

- corpus and manifest SHA-256;
- Vidrensic version;
- UTC start/finish timestamps;
- per-source SHA-256;
- expected vs actual values;
- explicit PASS/FAIL/ERROR reasons.

## Real recorder fixtures

Real-device validation must not be mixed casually with the redistributable synthetic corpus. For each real fixture, record externally or in a restricted companion manifest:

- manufacturer/OEM, model and firmware;
- drive/storage topology;
- acquisition method and write-blocking controls;
- source image hashes;
- how ground truth was established;
- channel count and known recording intervals;
- known deletions/overwrites/corruption injected or observed;
- expected recovered fragment/frame ranges;
- expected timestamps and tolerated uncertainty;
- validator identity and independent rerun information.

Do not commit active-case CCTV, personal data, credentials, encryption keys or non-redistributable samples to the public repository.

## Promotion policy

A format/family should move through capability stages only when the corpus supports the claim:

```text
DETECT -> PROFILE -> PARSE -> RECONSTRUCT -> VALIDATE
```

A recognizable signature does not promote a format to reconstruction support. A single recorder does not establish all firmware variants. A successful synthetic fixture does not substitute for real-device validation.

## Independent validation

The long-term goal is to publish a release qualification report that another examiner can reproduce from declared fixtures and hashes without developer intervention. Until then, Vidrensic remains alpha software under active forensic validation.
