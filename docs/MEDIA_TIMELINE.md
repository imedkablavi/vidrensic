# Media Timeline Analysis

Vidrensic can inspect the first video stream and build a bounded timing inventory for recovered media.

## Command

```bash
vidrensic-media recovered.mp4 \
  --out case/private/timeline.json \
  --timeline
```

The human-facing output stays concise. The JSON report records the detailed timing evidence.

## Recorded evidence

The report includes:

- stable SHA-256 and SHA-512 hashes of the tested artifact;
- frame count and keyframe count observed by the scan;
- keyframe timestamps;
- inferred frame rate from observed presentation timestamps;
- frame-rate confidence;
- non-monotonic PTS and DTS counts;
- duplicate PTS count;
- unusually large inter-frame gaps;
- a bounded anomaly map;
- whether the scan reached its configured safety limit.

## Review semantics

Clean timing is evidence about the tested media artifact, not proof of recorder provenance or legal authenticity. Any detected timing anomaly or bounded/truncated scan returns a review-required exit state so downstream automation cannot mistake an incomplete or inconsistent timeline for a clean result.

## Safety

The artifact is opened through the stable forensic hashing path before and after analysis. If the artifact changes during the timeline run, the analysis fails closed.

The external `ffprobe` process is resolved to an executable path, stdout is bounded, each frame record has a maximum line size, and the complete scan has a finite timeout.
