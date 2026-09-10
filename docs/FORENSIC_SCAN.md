# Forensic Media Scan

`vidrensic-forensic-scan` is the composite media qualification entrypoint. It combines stable SHA-256/SHA-512 identity checks, bounded ffprobe inventory, stream-structure checks, frame-rate consistency checks, optional timeline analysis, and optional decoder-error sampling.

## Profiles

`quick` runs the inventory checks and three-point decode QC. A clean quick scan is always `REVIEW` because most frames were not examined.

`standard` adds full frame-timeline analysis (PTS/DTS monotonicity, duplicate timestamps, large gaps, observed duration and inferred frame rate). A clean standard scan is still `REVIEW` because the decode is sampled rather than full.

`deep` performs full decode QC and complete frame-timeline analysis. It can return `PASS` only when:

- full decode succeeds;
- expected duration was supplied and is acceptable;
- timeline analysis is complete;
- no PTS/DTS/timestamp-gap anomalies are present;
- no other `REVIEW` or `FAIL` finding remains; and
- the artifact SHA-256/SHA-512 remains stable for the entire scan.

`--decoder-errors` adds bounded decode-window mapping. This is useful for locating damaged regions, but sampled coverage does not prove that unsampled frames are error-free.

## Findings

Findings use three severities:

- `INFO`: contextual information that does not lower the verdict by itself.
- `REVIEW`: a condition that needs examiner interpretation or an incomplete qualification scope.
- `FAIL`: a condition that invalidates the requested qualification, such as no video stream, a failed full decode, or an artifact changing during scanning.

An anomaly is not automatically evidence of deliberate manipulation. Container structure, timestamp behavior, frame-rate disagreement, and decode failures can arise from ordinary recorder behavior, export tooling, transport damage, or partial recovery.

## Evidence identity

The scanner hashes the artifact before and after the composite operation. The stable hash implementation also verifies the opened file's device/inode/size/timestamps and rejects pathname replacement or symlink substitution during hashing.

When the hashes differ between the beginning and end of the composite scan, the verdict is `FAIL` and the scan must not be treated as a valid qualification.

## Recommended workflow

For a newly recovered candidate, run `quick` first for triage. Use `standard` when timing continuity matters. Use `deep` only when the artifact and expected duration are known well enough to support a full qualification claim. Keep the generated JSON report with the case because it contains the hash identity, evidence bounds, findings, and component QC outputs.

Example:

```text
vidrensic-forensic-scan candidate.mp4 \
  --out reports/candidate.scan.json \
  --profile deep \
  --expected-duration 3600
```

No scan mode rewrites the input artifact. Repair, proxy generation, and cleanup remain separate derived-output workflows.
