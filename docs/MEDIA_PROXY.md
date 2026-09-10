# Controlled Transcode Proxy

`vidrensic-proxy` creates a deterministic, bounded H.264/AAC MP4 review proxy from a recovered video artifact.

## Purpose

The proxy exists for cases where the native or remuxed artifact is difficult for a reviewer/player to handle. It is a **derived review copy**, not forensic master media and not a corruption-repair operation.

The profile is fixed to:

- H.264 (`libx264`), preset `fast`, CRF 23;
- AAC audio at 128 kbps when an audio stream exists;
- `yuv420p` pixel format;
- MP4 with `+faststart`.

All parameters are recorded in the manifest.

## Safety

The source is validated as a regular non-symlink file and hashed before processing. It is probed and transcoded without writing to the source. After transcoding, the source is hashed again and any mutation causes failure.

The temporary output is private, bounded in size, probed, hashed and decode-smoke-tested before publication. It is published into the requested destination only when the destination path is still unused. Existing destinations are never replaced.

The manifest is written after output verification. If manifest publication fails, the derived proxy is removed so an untracked review artifact is not left behind.

## Example

```bash
vidrensic-proxy recovered.mp4 \
  --out recovered-review-proxy.mp4 \
  --manifest recovered-review-proxy.json
```

With a case:

```bash
vidrensic-proxy recovered.mp4 \
  --out recovered-review-proxy.mp4 \
  --manifest recovered-review-proxy.json \
  --case ./case.json
```

## Interpretation

A proxy can change encoding, bitrate, quality, timestamps, metadata, and unsupported streams. Its successful decode means the **proxy** is readable; it does not prove the original recovered media was intact or that missing/corrupted source content was recovered.
