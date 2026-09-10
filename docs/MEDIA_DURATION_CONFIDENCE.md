# Media duration confidence

Timeline reports keep `duration_seconds` as the container's nominal duration. They additionally expose an observed duration estimate derived from the first and last usable frame timestamps plus the median positive packet/frame duration.

The report separates these values so an analyst can see when metadata and observed timing disagree.

## Confidence rules

`High` requires enough frames, complete timeline traversal, no timing anomalies, and less than 1% difference between nominal and observed duration.

`Moderate` permits a difference below 5% when the evidence is otherwise usable. Any truncation, too few frames, missing timestamps, or larger disagreement lowers confidence to `Low`.

Timing anomalies also prevent a high-confidence duration claim. A low-confidence duration is a review signal, not proof of corruption.

## Example output

```text
Timeline analysis complete

Artifact     recovered.mp4
Duration     00:42 nominal
Observed     00:41 from frame timestamps
Duration QC  Moderate
Frames       1,050
Keyframes    42
Frame rate   25 fps
Timing       Stable
Coverage     Complete
Report       /case/timeline.json
```

The observed duration is an evidence-derived estimate. It should not be treated as a replacement for recorder-native timing metadata.
