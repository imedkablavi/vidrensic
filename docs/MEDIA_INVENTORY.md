# Media Artifact Inventory

Vidrensic can record a stable forensic inventory for a recovered media artifact without changing the artifact.

## Command

```bash
vidrensic-media recovered.mp4 \
  --out case/private/media-inventory.json
```

The default output is intentionally concise for an examiner. The JSON report contains the complete machine-readable inventory.

## Optional QC

Run the existing three-point decode checks while building the inventory:

```bash
vidrensic-media recovered.mp4 \
  --out case/private/media-inventory.json \
  --qc fast
```

For a full decode qualification:

```bash
vidrensic-media recovered.mp4 \
  --out case/private/media-inventory.json \
  --qc full \
  --expected-duration 3600
```

A full decode can only report `PASS` when the media decodes successfully, timing is acceptable, an expected duration is supplied, and no reconstruction ambiguity/unresolved state is attached by the caller.

## Recorded evidence

The inventory binds:

- SHA-256 and SHA-512 hashes from the stable forensic hashing path;
- artifact size;
- detected video codec, dimensions and frame-rate evidence;
- every stream reported by the bounded `ffprobe` probe;
- optional QC status, reasons, measurements and decode checkpoints.

The inventory JSON is written atomically with owner-only permissions and does not overwrite an existing report unless `--replace` is explicitly supplied.

## Claim boundary

A successful inventory establishes what was observed for the tested artifact during the inspection. It does not establish original recorder provenance, legal chain of custody, hardware authenticity or support for an untested recorder variant.
