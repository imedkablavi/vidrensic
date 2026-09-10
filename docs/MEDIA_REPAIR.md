# Remux-First Repair

`vidrensic-repair` provides the first conservative repair operation for recovered video artifacts: a **stream-copy remux**.

## What remux does

The operation asks `ffmpeg` to copy all source streams without transcoding while rebuilding the destination container. This can repair container-level structure, indexing, or muxing problems that prevent ordinary playback.

It does **not** repair corrupted H.264/H.265 payloads, invent missing frames, reconstruct damaged GOPs, or prove that an otherwise broken recording contains all original content.

## Safety model

The source is opened and hashed before processing, probed, and hashed again after the derived output has been produced. Any source mutation causes the operation to fail.

The destination is created as a private temporary file in the destination directory. It must not already exist and it must use a supported container extension. The temporary result is probed and hashed before publication. Publication uses a same-directory hard-link so a fully written file is made visible without replacing an existing path.

The manifest is written only after the destination has been verified. If manifest creation fails, the derived output is removed rather than leaving an untracked repair artifact.

## Example

```bash
vidrensic-repair recovered.mp4 \
  --out recovered-remux.mp4 \
  --manifest recovered-remux.json \
  --mode remux
```

With a forensic case:

```bash
vidrensic-repair recovered.mp4 \
  --out recovered-remux.mp4 \
  --manifest recovered-remux.json \
  --case ./case.json
```

The JSON manifest records the source and destination hashes, sizes, codec/duration information, stream counts, the repair mode, and the explicit limitation that compressed payload corruption is not repaired.

A remux result is a **derived review artifact**. It must not be treated as a replacement for the original recovered media.
