# Anonymized Profiler Bundle

Vidrensic can turn an unknown-recorder triage result into a compact support bundle that contains profiler signals without the source evidence.

## Command

```bash
vidrensic-profiler recorder-image.raw \
  --out profiler-bundle.json
```

The command runs the normal bounded triage workflow first, then removes source-specific identifiers before writing the bundle.

## What is included

- Vidrensic version and bundle schema version;
- source kind (`file` or `block-device`), approximate size bucket, read-only state and mounted state;
- partition scheme, sector size, partition count and filesystem family/confidence bands;
- sample count/size bucket and aggregate statistical ranges for entropy and byte composition;
- signature counts without retained offsets;
- ranked format families with confidence bands;
- the next recommended workflow stage.

## What is deliberately removed

The anonymized bundle does not contain source paths, source filenames, source SHA-256/SHA-512 values, serial numbers, device WWNs, filesystem GUIDs, partition names, exact signature offsets, raw signature bytes or evidence content.

The bundle is still written with owner-only `0600` permissions and does not overwrite an existing report unless `--replace` is explicitly supplied.

## Support workflow

A practitioner can share the anonymized bundle with a format-profile developer to help decide whether a new recorder family or firmware variant deserves investigation. The original evidence stays under the examiner's control.

An anonymized profiler bundle is investigative metadata, not validation evidence. It cannot establish that a recorder family is supported or that a recovery result is correct.
