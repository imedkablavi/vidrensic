# Duplicate and Near-Duplicate Analysis

`vidrensic-duplicates` compares recovered video artifacts for exact and visual similarity.

## Method

1. Each source is validated as a regular non-symlink file and receives SHA-256/SHA-512 identity hashes.
2. Identical SHA-256 values are classified as `EXACT` without relying on visual similarity.
3. Non-identical videos are sampled at evenly distributed timestamps and converted to 9x8 grayscale frames.
4. Each frame is reduced to a 64-bit dHash. Corresponding sample positions are compared with Hamming distance.
5. `NEAR_DUPLICATE_CANDIDATE` requires both the configured median similarity threshold and at least 80% of samples above the per-frame threshold.

The result is an analyst triage signal. `NEAR_DUPLICATE_CANDIDATE` does not prove that two recordings are the same source, camera, event, or file lineage.

## Example

```bash
vidrensic-duplicates clip-a.mp4 clip-b.mp4 clip-c.mp4 \
  --samples 32 \
  --threshold 0.90 \
  --frame-threshold 0.80 \
  --out duplicates.json
```

The JSON report records source hashes, nominal durations, sampling parameters, pair classifications, similarity scores, matched-frame ratios, and duration ratios.

## Safety boundaries

The analyzer uses bounded ffmpeg output and limits the maximum sample count and input-set size. A source that cannot produce a complete comparable frame set is classified `REVIEW` rather than being treated as distinct. Output reports use the same owner-only permissions and no-overwrite behavior as other forensic reports.
