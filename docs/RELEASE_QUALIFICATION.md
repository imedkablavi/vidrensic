# Release qualification

A release artifact is **qualified for the tests actually executed**, not certified for every recorder or forensic use case. This document defines the minimum evidence that should accompany a Vidrensic release.

## Mandatory automated gates

For the release commit:

1. Ruff and bytecode compilation succeed.
2. The full unit/synthetic test suite passes.
3. Overall and forensic-critical coverage gates pass in normal CI.
4. The real-recorder corpus admission index passes schema/provenance validation.
5. The public validation corpus runs and its declared synthetic expectations pass.
6. The WFS production selector and reference branch-and-bound selector agree on the deterministic profiling fixture used by the workflow.
7. Source distribution and wheel build successfully.
8. `twine check` accepts package metadata.
9. The built wheel installs and `pip check` succeeds.
10. The installed wheel reruns the public validation corpus successfully.
11. A CycloneDX 1.6 JSON SBOM is generated from an isolated Python environment containing the built wheel and its resolved runtime dependencies, and CycloneDX validation succeeds.
12. Release artifacts, qualification JSON, SBOM and build manifest receive SHA-256 checksums and the checksum file verifies before upload.
13. For a tag publication, the read-only build job completes before the separate publication job receives write permission.
14. For a tag publication, every qualified payload file is signed with Sigstore keyless signing and its bundle is verified against the repository/ref/commit identity before upload to the GitHub Release.

`workflow_dispatch` is a qualification/build path only. It does not publish a GitHub Release and does not create a signed-release claim.

## Evidence shipped with a qualifying release build

The release workflow is expected to retain:

- wheel and source distribution;
- `BUILD-MANIFEST.json` with commit/ref/workflow/runtime identity and claim limits;
- `SOURCE-VALIDATION-REPORT.json`;
- `WHEEL-VALIDATION-REPORT.json`;
- `SOLVER-PROFILE.json`;
- `REAL-CORPUS-INDEX.json`;
- `QUALIFICATION-DEPENDENCIES.json`;
- `SBOM.cdx.json` in CycloneDX 1.6 JSON format;
- `SHA256SUMS.txt`.

A tag-published GitHub Release must additionally contain the Sigstore bundle generated beside every qualified payload file. If signing or verification fails, the publication job must fail before `gh release upload`.

These reports are build evidence. They are not substitutes for a case-specific examiner report.

## Supply-chain permission boundary

The qualification/build job has read-only repository contents permission. It cannot publish a release.

The publication job runs only for tag refs, depends on the successful build job, downloads the already-qualified workflow artifact, re-verifies its SHA-256 checksum file, and receives only the additional permissions required for publication and keyless signing: Actions artifact read, repository contents write for release upload, and OIDC `id-token: write` for Sigstore.

The signing step creates public transparency-log records and therefore exposes the GitHub Actions signing identity as intended by the Sigstore model.

## PASS boundaries

### CI/test PASS proves

Only that the declared checks ran successfully for the exact commit/environment represented by that workflow run.

It does not prove:

- universal DVR/NVR compatibility;
- absence of parser defects or vulnerabilities;
- evidentiary admissibility in a jurisdiction;
- independent forensic certification;
- absence of false positives/false negatives outside the tested corpus;
- correctness for firmware/device variants not represented by admitted fixtures.

### Public validation-corpus PASS proves

Only the machine-readable expectations for the exact public synthetic fixtures passed. The public corpus is intentionally synthetic and cannot be cited as real-recorder compatibility evidence.

### Real-recorder index validation PASS proves

Only that admitted case metadata satisfies the provenance/ground-truth admission schema. An empty index can therefore pass schema validation while proving **zero** recorder-family compatibility.

### A future real-recorder case PASS would prove

Only that the declared expectations for the exact hashed fixture, fixture version, ground-truth record and Vidrensic commit were met within declared tolerances. Promotion of a recorder family requires multiple representative fixtures and should not be generalized beyond their documented variants.

### Solver equivalence/profile PASS proves

Only that the current deterministic synthetic profile selected the same hypothesis set and the profiling script completed within configured bounds. Timing is runner-specific. The reference branch-and-bound implementation is not the production recovery selector.

### SBOM generation PASS proves

Only that the release workflow produced a syntactically valid CycloneDX inventory for the isolated Python runtime environment used to install the built wheel. It does not enumerate operating-system packages, firmware, external tools such as FFmpeg/ddrescue, or dependencies that are not present in that Python environment unless they are represented separately.

### Sigstore verification PASS proves

Only that the published payload matched the signed bytes and that the signing certificate/bundle satisfied the GitHub Actions repository/ref/commit verification policy used by the workflow at publication time. It does not prove the software is vulnerability-free, reproducibly built, independently certified, or legally admissible.

The current signing bundles are artifact signatures with transparency-log evidence. Do not label them a complete SLSA provenance attestation unless a separate provenance predicate/attestation is generated and verified.

## Manual gates before a public stable release

The following remain manual or require evidence not safely fabricated in CI:

- legally authorized real-recorder fixture review across supported families/firmware variants;
- independent rerun/lab review where the deployment policy requires it;
- installer behavior on supported deployment environments beyond the Linux wheel CI path;
- provenance/version review for external native tools such as FFmpeg, ffprobe, ddrescue and smartctl;
- social-preview rendering and public release-page presentation;
- examination of any restricted fixture without publishing protected evidence;
- GitHub repository ruleset/branch-protection and account-level security-setting verification.

A workflow must not convert a missing manual gate into PASS. Use `UNKNOWN`, `REVIEW` or an explicit release blocker.
