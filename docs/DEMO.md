# Reproducible Public Demo

This demo is intentionally synthetic. It contains **no real CCTV footage and no case evidence**. Its purpose is to let a new user verify a small, deterministic Vidrensic detection/recovery path without implying recorder-family validation.

## 1. Install the development build

```bash
git clone https://github.com/imedkablavi/vidrensic.git
cd vidrensic
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
```

Record the version before comparing output:

```bash
vidrensic --version
```

## 2. Run the complete demo

```bash
bash examples/run_demo.sh
```

The script creates a deterministic synthetic DHAV-like source, prints its SHA-256 hash, asks Vidrensic to rank format evidence, then performs structurally validated frame carving/channel demultiplexing.

Expected shape of the output:

```text
[demo] generating deterministic synthetic recorder source
[demo] source=.../synthetic-dhav.raw
[demo] frames=12 channels=2
[demo] sha256=<deterministic hash>

[demo] format detection
... dhav ... RECONSTRUCT ...

[demo] recovery
.../recovered/dhav_manifest.json

[demo] recovered channels
channel_00.native.dhav
channel_00.video.es
channel_01.native.dhav
channel_01.video.es
```

Exact confidence text may evolve as detectors improve. The regression test asserts the narrower invariant: **the documented synthetic source ranks DHAV first and all 12 structurally valid synthetic frames remain recoverable into two physical channels.**

## 3. Run the public validation corpus

The demo and the validation corpus are separate checks. Run both when evaluating a checkout:

```bash
vidrensic validate corpus validation_corpus/corpus.json \
  --out validation-report.json
python -m json.tool validation-report.json | less
```

A report-level `PASS` here applies only to the declared expectations for the exact public synthetic corpus. The real-recorder admission index is separate under `validation_corpus/real/` and may truthfully contain zero fixtures.

## 4. Run the demo steps manually

Generate only the sample:

```bash
python examples/generate_dhav_demo.py --out .vidrensic-demo/synthetic-dhav.raw
```

Rank formats:

```bash
vidrensic formats detect .vidrensic-demo/synthetic-dhav.raw
```

Recover channels:

```bash
vidrensic recover dhav .vidrensic-demo/synthetic-dhav.raw \
  --out .vidrensic-demo/recovered
```

Inspect the manifest rather than relying on filenames alone:

```bash
python -m json.tool .vidrensic-demo/recovered/dhav_manifest.json | less
```

## What this demo proves — and what it does not

It proves that the tested build can recognize the documented synthetic DHAV structure, validate its synthetic frame boundaries/footer lengths, preserve physical ordering, split frames by channel, extract elementary video payload bytes and emit a manifest.

It does **not** prove support for every Dahua/OEM firmware, circular-wrap chronology, deleted-recording recovery, audio payload correctness, vendor encryption, a specific real recorder, evidentiary admissibility or independent forensic certification.

The demo itself never upgrades a family to validated real-recorder support. That requires admitted, legally usable real fixtures with hashes, provenance and independent ground truth.

## Why the demo is kept in CI

`tests/test_demo_example.py` executes the generator and validates the resulting source against the actual detector/scanner. This prevents the public quick-start path from silently becoming stale while parsers evolve.

For release claim boundaries, see `docs/RELEASE_QUALIFICATION.md` and the standalone validation report for the audited release/commit.
