# Recorder Sample Submission Policy

Vidrensic grows through reproducible format evidence, but surveillance data is often sensitive. This document defines the minimum handling standard for samples used to add or validate a recorder family/variant.

## Never post active-case evidence to a public issue

Do **not** upload CCTV footage, credentials, device passwords, encryption keys, faces, vehicle plates, audio conversations, personal data, or full forensic images to a GitHub issue or pull request.

A public format request should contain only non-sensitive metadata: vendor/model/firmware, disk topology, signatures, sanitized command output, offsets, sizes, checksums of intentionally shared synthetic/sanitized samples, and a description of the failure mode.

## Preferred sample order

1. **Synthetic fixture** reproducing the parser structure.
2. **Vendor-generated lab recording** made specifically for testing.
3. **Sanitized bounded sample** containing the smallest range required to reproduce the format behavior.
4. Full evidence images only under an organization-approved evidence-transfer process; never through a public GitHub attachment.

## Minimum metadata

Every accepted fixture should document:

- vendor / OEM label;
- exact recorder model and firmware if known;
- source type: physical disk, raw image, exported file, RAID/JBOD set;
- disk count/capacity and known storage geometry;
- how the sample was acquired;
- sample byte range and why that range is sufficient;
- SHA-256 and SHA-512 hashes;
- expected parser/recovery result;
- whether timestamps are native, derived, or unknown;
- known corruption, overwrite, bad-sector, or circular-wrap conditions;
- authorization to analyze and share the supplied material.

## Create the smallest defensible sample

For a block device, inspect read-only state first and acquire a bounded range using a forensic imaging workflow. Never trim the only copy of evidence in place.

For example, a lab sample may be hashed with:

```bash
sha256sum sanitized-sample.raw
sha512sum sanitized-sample.raw
```

When a small range is sufficient, record its original physical offset in the accompanying metadata so parser tests can preserve that context.

## Sanitization requirements

Sanitization must not silently change the structure being studied. If payload bytes are replaced, the fixture documentation must state exactly what was modified and which structural fields remain original.

For video-bearing samples, prefer purpose-built lab recordings over attempting to anonymize real CCTV. Re-encoding real evidence can destroy the proprietary framing, timestamps, allocation behavior, and corruption pattern that the parser needs to reproduce.

## Encryption keys and credentials

Never include key bytes, passwords, recovery codes, or device credentials in public fixtures. Vidrensic crypto receipts use key fingerprints specifically so a transform can be documented without publishing the secret.

## Fixture acceptance

A new recorder variant should not be promoted to validated recovery support from one unexplained sample. The expected path is:

```text
request
  -> structural evidence
  -> bounded fixture
  -> parser/profile
  -> regression tests
  -> malformed/corruption tests
  -> independent or second-fixture confirmation
  -> capability level update
```

See `docs/FORMAT_ONBOARDING.md` and `docs/VALIDATION.md` for the engineering and release gates.
