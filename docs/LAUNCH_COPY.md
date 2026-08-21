# Vidrensic launch copy

Use these as starting points after the repository is public and the first alpha release is published. Adapt each post to the community's rules; do not mass-post identical text.

## Short announcement

**Vidrensic 0.5 alpha — forensic-first DVR/NVR evidence reconstruction**

Vidrensic is a Linux-first project for proprietary surveillance-storage triage, acquisition, reconstruction and validation. The project focuses on failure modes such as lost indexes, circular storage, interleaved channels, fragmentation, uncertain timestamps and partially damaged recordings rather than treating DVR disks as ordinary file recovery.

The public alpha includes WFS and DHAV reconstruction foundations, unknown-recorder triage, acquisition receipts, codec-aware native extraction, known-key AES transforms, strict capability stages, and a deterministic synthetic demo that needs no CCTV evidence.

Try the demo:

```bash
bash examples/run_demo.sh
```

Useful feedback: sanitized recorder/firmware format observations, synthetic fixtures, parser edge cases, reproducible recovery failures and validation methodology.

Please do not upload active-case footage, credentials or cryptographic keys.

## Technical forum version

I have been building **Vidrensic**, a forensic-first DVR/NVR storage reconstruction project. The design goal is to keep detection, profiling, parsing, reconstruction and validation as separate capability levels so a recognizable signature is never presented as proof of full recovery support.

Current alpha work includes:

- read-only source safety and ddrescue acquisition/verification receipts;
- streaming unknown-recorder signature mapping and triage;
- WFS profiling/date scan/reconstruction foundations;
- DHAV structural validation, metadata parsing and physical channel demux;
- generic Annex-B H.264/H.265 and MPEG-PS/PES evidence detection;
- proprietary Hikvision Master Sector profiling without claiming full HIKBTREE recovery;
- source provenance, time-evidence modeling, audit chains and known-key AES transforms;
- synthetic/malformed-input regression tests and installed-wheel QA.

There is a deterministic synthetic DHAV demo in the repository so the parser/recovery path can be tested without sharing surveillance footage.

I am particularly interested in legally shareable/synthetic fixtures and documentation for recorder filesystem/container variants, especially where firmware changes the structure.

## Release tagline

> Reconstruct the recording. Preserve the evidence.

## Suggested first-launch keywords

`digital forensics`, `video forensics`, `DVR`, `NVR`, `CCTV`, `surveillance`, `video recovery`, `data recovery`, `WFS`, `DHAV`, `H.264`, `HEVC`, `forensic tooling`
