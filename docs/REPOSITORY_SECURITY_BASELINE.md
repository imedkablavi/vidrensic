# Repository and release security baseline

This document records repository-level controls that protect Vidrensic source, review gates and release artifacts. It is separate from forensic-format validation: a secure repository does not prove recorder compatibility, and a passing parser corpus does not prove repository governance.

## Observed repository state - 2026-08-24

At the start of this hardening pass, GitHub reported the default `main` branch as **not protected** and with no enforced required status checks. That is a repository-governance gap even when the current CI, Security and CodeQL workflows are green.

Repository settings are not controlled by Vidrensic runtime code. The controls below must therefore be enabled in GitHub repository settings/rulesets and verified separately from CI.

## Required `main` protection before a stable release

Configure a branch ruleset or branch protection rule for `main` with these minimum properties:

1. Require changes to reach `main` through a pull request.
2. Require the `CI`, `Security` and `CodeQL` checks that are applicable to the pull request before merge.
3. Require all review conversations to be resolved.
4. Block force pushes and branch deletion.
5. Do not allow administrators or automation to bypass the rule routinely; document any emergency bypass.
6. Require the branch to be up to date before merge when that does not create an unsustainable merge queue.
7. Prefer signed commits/tags for release-bearing changes when the maintainer workflow supports them.

For a single-maintainer repository, do not enable a mandatory external approval count unless a real independent reviewer is available. Required automated checks and resolved review conversations are still useful and enforceable.

## GitHub security settings to verify

Enable and verify, where the GitHub plan/repository supports them:

- Dependabot alerts and Dependabot security updates;
- secret scanning and push protection;
- private vulnerability reporting;
- a restrictive default GitHub Actions token permission (`contents: read` unless a workflow explicitly needs more);
- approval restrictions for workflows originating from untrusted forks when applicable;
- release/tag protection or rulesets for production release tags.

These are configuration checks. They must not be represented as enabled until verified in GitHub settings.

## Workflow supply-chain rules

Vidrensic workflows should follow these rules:

- third-party GitHub Actions are pinned to immutable commit SHAs, with the human-readable release tag retained only as a comment;
- a repository-local Security gate rejects mutable external Action references;
- jobs have explicit time limits;
- ordinary CI, CodeQL and security scans use read-only repository permissions except for the narrowly required CodeQL `security-events: write` permission;
- release qualification/build runs with read-only repository contents permission;
- release publication is a separate tag-only job and is the only workflow path that receives repository contents write permission;
- downloaded/build-time dependencies are treated as untrusted executable code and release-only tooling is version pinned in the workflow;
- checksums, validation reports, SBOMs and signatures are evidence with explicit claim limits, not proof of recorder compatibility.

### Release-token boundary

The release pipeline separates build/qualification from publication. The build job cannot write repository contents. The tag-only publish job depends on the successful build, downloads the qualified artifact from the same workflow run, re-verifies its SHA-256 checksum file, and receives only Actions artifact read, repository contents write, and OIDC identity-token permission.

A `workflow_dispatch` execution produces qualification artifacts but skips the publication/signing job and therefore must not be described as a signed GitHub Release.

## Artifact integrity

Release qualification produces:

- SHA-256 checksums;
- a build manifest with commit/ref/workflow identity and claim limits;
- source and installed-wheel validation reports;
- a deterministic solver profile;
- the real-recorder admission index;
- a direct resolved-runtime dependency inventory;
- a CycloneDX 1.6 JSON SBOM generated from an isolated environment containing the built wheel and resolved Python runtime dependencies.

For tag publication, the qualified files are signed using Sigstore keyless GitHub Actions identity. Every generated bundle is verified against the repository, ref and commit before GitHub Release upload. Signing or verification failure blocks publication.

These controls improve artifact origin/integrity but do **not** establish all of the following:

- operating-system/native-tool SBOM coverage;
- a complete SLSA provenance predicate/attestation;
- reproducible-build proof;
- independent trusted laboratory certification;
- evidence admissibility.

Sigstore transparency records intentionally disclose the CI signing identity. The current artifact bundles must not be called complete SLSA provenance unless a separate provenance attestation is generated and verified.

## Evidence-host privacy baseline

A newly created Vidrensic case must protect case-owned directories and metadata from unrelated local users by default. Current hardening sets case directories to owner-only (`0700`) and core metadata/audit/job database files to owner read/write (`0600`) on the supported Linux platform.

The public-release hygiene gate also rejects tracked files under case/evidence acquisition roots and common recorder/media evidence suffixes unless an exact repository path is explicitly reviewed and allowlisted.

This is a local filesystem access and repository-publication baseline, not encryption at rest. Full-disk or case-volume encryption, operating-system account isolation, backup policy and evidence-retention policy remain deployment responsibilities.

## External tool isolation

FFmpeg/ffprobe, GNU ddrescue, smartctl and similar tools process attacker-controlled or damaged data and are separate attack surfaces.

Current media-tool hardening includes:

- no shell interpolation;
- finite default ffprobe and decode-window timeouts;
- full-video decode is bounded by a finite default timeout and requires any override to remain a positive finite duration;
- ffprobe requests only the media fields Vidrensic currently needs instead of dumping all format/stream metadata;
- ffprobe JSON is rejected if it exceeds the configured safety limit;
- decoder diagnostics stored in QC output are truncated to a fixed maximum size;
- FFmpeg decode checks use `-nostdin` and `-xerror` so interactive input is disabled and decode errors terminate the validation path rather than generating an unbounded error stream;
- regression tests cover malformed JSON, oversized probe output, diagnostic truncation, timeout validation and the FFmpeg fail-fast flags.

These controls reduce hang/log/output-amplification risk but are **not** a process sandbox. Stable-release qualification still needs:

- documented minimum/maximum supported FFmpeg/ffprobe versions;
- sandbox/container guidance for especially hostile media;
- operating-system resource caps if a supported deployment model can enforce them without invalidating legitimate large evidence;
- equivalent review of every remaining external tool path (GNU ddrescue, smartctl and future adapters);
- crash and timeout fixtures against the real supported tool versions.

## What this baseline proves

A PASS of repository CI can show that the checked commit met the automated gates configured in that workflow. It cannot prove that GitHub repository settings were enabled, that every native dependency is represented in the Python SBOM, that a recorder family is validated, that FFmpeg is sandboxed, that a complete SLSA provenance exists, or that a deployment host is securely configured.
