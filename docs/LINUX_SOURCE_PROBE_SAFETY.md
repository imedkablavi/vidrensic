# Linux source-probe safety

Vidrensic inspects Linux block-device state before acquisition. These checks are safety inputs; an unavailable or malformed mount-safety probe must not be interpreted as proof that a device is safe.

## Bounded native-tool output

`blockdev` and `lsblk` output is directed to temporary files rather than `subprocess.PIPE`, then read through explicit byte limits. This prevents a broken or replaced helper executable from making Python buffer an unbounded stdout/stderr stream in memory before validation runs.

The current limits are intentionally much larger than normal util-linux output:

- `blockdev` stdout: 64 KiB;
- `blockdev` stderr: 64 KiB;
- `lsblk` descendant `MAJ:MIN` stdout: 2 MiB;
- `lsblk` identity JSON stdout: 1 MiB;
- `lsblk` stderr: 256 KiB.

The helper executable is resolved to an absolute path for each probe invocation. This is execution determinism for that invocation, not package-authenticity verification.

## Mount-safety fail-closed behavior

For block-device acquisition, descendant enumeration is part of the mount-safety decision. If `lsblk` descendant enumeration times out, exits non-zero, exceeds its output limit, returns non-ASCII output, or emits a malformed `MAJ:MIN` value, source inspection fails instead of assuming that no descendant partitions/LVs exist.

`/proc/self/mountinfo` is streamed with a 32 MiB total limit and a 256 KiB logical-line limit. Missing or malformed mountinfo also fails source inspection for a block device rather than being converted to an empty mount list.

This protects against a dangerous false-negative state where a mounted descendant might otherwise be missed.

## Best-effort identity is separate

Serial, WWN and model values from `lsblk -J` improve source binding across device-node renumbering, but they are not required for the mount-safety decision. Identity-probe failure or oversized/malformed identity JSON returns no hardware identifiers and leaves Vidrensic on its documented weaker identity fallback. It does not invent a serial or WWN.

## Claim boundary

These checks bound local process memory use and make block-device mount-state probing fail closed when the safety inputs cannot be trusted. They do not prove that util-linux binaries are vendor-authentic, do not replace a hardware write blocker, do not attest kernel `/proc`/`/sys` truth, and do not establish forensic chain of custody by themselves.
