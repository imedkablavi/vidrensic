# Decoder error region analysis

`vidrensic-media <artifact> --out <report> --decoder-errors` runs a bounded sequence of video decode windows and records windows where FFmpeg reports a decode failure.

## What the report means

The report is a **sampled decoder-error map**. A reported region is the union of adjacent failed decode windows. It is not an exact byte range, exact damaged frame interval, or proof that the failure begins or ends at the displayed timestamp.

A clean result means only that the sampled windows decoded successfully. It does not prove that unsampled time ranges are free from decoder errors.

The report is hash-bound. The artifact is hashed before and after analysis; if the source changes while the scan is running, the operation fails closed.

## Bounded behavior

The default is a four-second window with at most 512 windows. For media longer than the natural scan budget, the tool increases the stride so the number of decode processes remains bounded. The report records the effective stride and `coverage_fraction`.

The exit code is `0` only when the sampled coverage is complete and no sampled decode window fails. A non-zero result means the examiner should review the report; it does not by itself prove corruption.

## Example

```text
vidrensic-media evidence.mp4 --out decoder-errors.json --decoder-errors
```

For machine-readable output:

```text
vidrensic-media evidence.mp4 --out decoder-errors.json --decoder-errors --json
```

For large cases, tune the sampling explicitly:

```text
vidrensic-media evidence.mp4 --out decoder-errors.json --decoder-errors \
  --window-seconds 8 --max-windows 512 --timeout 30
```

## Forensic use

Use decoder-error regions as triage evidence alongside native stream metadata, PTS/DTS analysis, keyframes, and full decode results. Do not convert sampled failures directly into a claim about the physical location or cause of corruption.
