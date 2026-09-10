# Evidence Export

Vidrensic can create a verified byte-for-byte copy of a recovered artifact and bind both source and destination hashes in a private manifest.

## Command

```bash
vidrensic-export recovered.mp4 \
  --out case/exports/recovered.mp4 \
  --manifest case/exports/recovered.json
```

The default terminal output is deliberately concise. The manifest contains the complete hashes and verification metadata.

## Profiles

Use `--profile master` for a forensic preservation copy or `--profile review` for an exact review copy. The current exporter performs no media transformation; both profiles therefore preserve identical bytes. Future derived-media transforms must produce a separate artifact and provenance record rather than modifying the master copy.

## Safety properties

- source must be a regular non-symlink file;
- destination is created with `O_EXCL` and owner-only permissions;
- source identity is checked before and after the copy;
- destination is re-hashed after the copy;
- a mismatch removes the partial destination and fails closed;
- the private manifest is written atomically with owner-only permissions;
- an existing destination is never overwritten automatically.

## Claim boundary

A successful export establishes that the destination bytes match the source bytes observed during the export operation. It does not create a new acquisition record, establish legal chain of custody, or prove the origin/authenticity of the source artifact.
