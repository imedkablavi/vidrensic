# Vidrensic 0.5 alpha — release notes

Vidrensic 0.5 is the first milestone intended for controlled public alpha evaluation. It is **not** an independently certified forensic tool and does not claim universal DVR/NVR recovery.

## Highlights

- forensic-first source inspection and read-only safety checks;
- GNU ddrescue acquisition planning, resumable map handling and verification receipts;
- unknown-recorder triage and streaming physical signature hit maps;
- WFS detection/profiling/date scan and conservative reconstruction foundations;
- codec-neutral WFS native extraction with evidence-driven H.264/H.265/ES naming;
- DHAV structural validation, metadata parsing, channel demultiplexing and native/ES hashing;
- Hikvision proprietary-storage profiling without overclaiming HIKBTREE recovery;
- Annex-B H.264/H.265 and MPEG-PS/PES evidence detection;
- MBR/GPT and common filesystem signature profiling without mounting evidence;
- file/JBOD/RAID0 random-access source foundations;
- known-key AES-CBC/AES-CTR transformations with auditable receipts and key fingerprints;
- source identity, hash-chained case audit and native-vs-derived time evidence;
- generic node-disjoint global reconstruction solver foundation;
- deterministic synthetic public demo requiring no CCTV evidence.

## Validation and QA

The normal CI matrix covers Python 3.11, 3.12 and 3.13 and gates:

- Ruff static checks;
- Python compileall;
- unit, synthetic and malformed-input regression tests;
- minimum total coverage gate;
- CLI and import smoke tests;
- dependency consistency checks;
- sdist and wheel build;
- installation and smoke testing of the built wheel;
- deterministic public-demo regression.

A separate security workflow now gates:

- `pip-audit` against installed project dependencies;
- a tracked-text public-hygiene scan for common credential/secret patterns and suspicious local evidence paths;
- Gitleaks `v8.30.1` against the complete Git history with redacted output.

The public-readiness audit discovered that the previous `cryptography 46.x` dependency line was affected by current advisories. Vidrensic now requires the patched `cryptography >=50,<51` series, and the full CI matrix is used to verify compatibility with the supported Python versions.

## Current support maturity

| Family | Maturity | Notes |
|---|---:|---|
| WFS | RECONSTRUCT | conservative/local reconstruction; path-dependent global solving and frame-level overwrite salvage remain incomplete |
| DHAV | RECONSTRUCT | physical-order structural recovery and channel demux; circular chronology and broader audio/variant validation remain incomplete |
| Hikvision proprietary storage | PROFILE | Master Sector discovery/geometry profiling only; HIKBTREE recovery is not yet claimed |
| Annex-B H.264/H.265 | PARSE | codec/parameter-set evidence only |
| MPEG-PS/PES | PARSE | generic container evidence only |

The live `vidrensic formats list` output and `docs/SUPPORT_MATRIX.md` are authoritative when documentation differs.

## Known limitations

This alpha does **not** claim validated support for:

- universal DVR encryption/key recovery;
- WFS frame-level partially overwritten recording salvage;
- all Hikvision HIKBTREE/data-block variants;
- RAID5/6 parity reconstruction;
- E01/Ex01/AFF4 adapters;
- synchronized graphical review workstation;
- court-ready signed forensic export packages;
- every vendor, OEM, model or firmware using a familiar extension or branding.

## Try it safely

No real evidence is required for the public demo:

```bash
bash examples/run_demo.sh
```

For real evidence, use a hardware write blocker where available and inspect source safety before acquisition or parsing.

## Research and contributions

- Support matrix: `docs/SUPPORT_MATRIX.md`
- Validation policy: `docs/VALIDATION.md`
- Sample handling: `docs/SAMPLE_SUBMISSION.md`
- Contributing: `CONTRIBUTING.md`
- Citation metadata: `CITATION.cff`

Do not upload active-case CCTV, credentials, cryptographic keys or data you are not authorized to redistribute.
