# Doctor native-tool probe safety

`vidrensic doctor` is an environment readiness check. It does not certify native tools for forensic use.

## Probe behavior

For each configured native dependency, Vidrensic:

- resolves the discovered path to an absolute executable regular file;
- runs only the tool's version command, without a shell;
- disables stdin;
- uses a finite 5-second timeout;
- directs stdout/stderr to temporary files rather than `subprocess.PIPE`;
- reads at most 64 KiB from stdout and 64 KiB from stderr into Python memory;
- marks the tool unavailable if version output exceeds those bounds or the command fails.

A mandatory source-safety dependency that fails this probe makes `core_ready` false.

## Operator commands

Run the environment report:

```bash
vidrensic doctor
```

For the source-safety dependencies, confirm which binaries your shell resolves:

```bash
command -v findmnt lsblk blockdev
findmnt --version | head -n 1
lsblk --version | head -n 1
blockdev --version | head -n 1
```

For acquisition and media capabilities when installed:

```bash
command -v ddrescue smartctl ffprobe ffmpeg
ddrescue --version | head -n 1
smartctl --version | head -n 1
ffprobe -version | head -n 1
ffmpeg -version | head -n 1
```

Package-manager provenance and signatures should be recorded separately when release or forensic policy requires them. A successful version probe is not vendor authenticity, package signature verification, sandboxing, or independent forensic validation.
