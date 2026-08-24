# Media tool execution safety

Vidrensic uses `ffprobe` and `ffmpeg` only for media probing and validation. These tools are external native dependencies; their presence does not prove that a recorder family is supported or validated.

## Runtime bounds

The media execution path resolves `ffprobe` / `ffmpeg` to an absolute executable regular-file path immediately before invocation and does not use shell execution.

Process stdout/stderr are directed to temporary files rather than `subprocess.PIPE`, and only bounded prefixes are read back into Python memory:

- ffprobe JSON stdout: **2 MiB** maximum accepted payload;
- ffprobe/ffmpeg diagnostic stderr retained in memory: **64 KiB**;
- unexpected ffmpeg stdout retained in memory: **4 KiB**;
- all probe/decode calls require a finite positive timeout;
- decode validation uses `-nostdin` and `-xerror`.

If ffprobe JSON exceeds the accepted bound, the probe fails before JSON parsing. If ffmpeg diagnostics exceed the retained bound, the QC result keeps a bounded diagnostic prefix with an explicit truncation marker. Unexpected oversized ffmpeg stdout fails the decode check closed.

Temporary-file capture bounds Python memory reads, but it is not a native-process sandbox and does not guarantee temporary-storage capacity against a hostile or defective executable.

## Operator checks

On the Linux host used for validation, confirm the actual executables that will be found in `PATH`:

```bash
command -v ffprobe
command -v ffmpeg
ffprobe -version | head -n 1
ffmpeg -version | head -n 1
```

Run Vidrensic's environment check as well:

```bash
vidrensic doctor
```

For a release qualification record, capture the package-manager provenance separately when available (for example the distro package name/version and repository metadata). Vidrensic's absolute-path resolution is not a package signature check and does not establish vendor authenticity.

## Forensic claim boundary

A successful media probe or full decode proves only what the recorded QC evidence shows for the tested media artifact. It does not prove original recorder provenance, legal chain of custody, absence of prior transcoding, hardware authenticity, or compatibility with an untested recorder model.
