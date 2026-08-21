# Reproducible Demo

This demo is intentionally synthetic. It contains **no real CCTV footage and no case evidence**. Its purpose is to let a new contributor verify Vidrensic's format detection and DHAV channel reconstruction path in under a minute.

## 1. Install the development build

```bash
git clone https://github.com/imedkablavi/Video-Forensics.git
cd Video-Forensics
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
```

## 2. Run the complete demo

```bash
bash examples/run_demo.sh
```

The script creates a deterministic synthetic DHAV-like source, prints its SHA-256 hash, asks Vidrensic to rank the format families, then performs validated frame carving/channel demultiplexing.

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

Exact confidence text may evolve as detectors improve; the regression test asserts the important invariant: **DHAV must rank first and all 12 structurally valid frames must remain recoverable into two physical channels.**

## 3. Run the steps manually

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

Inspect the manifest:

```bash
python -m json.tool .vidrensic-demo/recovered/dhav_manifest.json | less
```

## What this demo proves — and what it does not

It proves that the installed build can recognize the documented synthetic DHAV structure, validate frame boundaries/footer lengths, preserve physical ordering, split frames by channel, extract elementary video payload bytes, and emit a manifest.

It does **not** prove support for every Dahua/OEM firmware, circular-wrap chronology, deleted-recording recovery, audio variants, vendor encryption, or a specific real recorder. Those capabilities remain governed by the live support matrix and validated fixture corpus.

## Why the demo is kept in CI

`tests/test_demo_example.py` executes the generator and validates the resulting source against the actual detector/scanner. That prevents the public quick-start demo from silently becoming stale while the parser evolves.
