# Forensic Format Onboarding

Vidrensic is designed to grow by **validated storage/record families and variants**, not by adding vendor names to a marketing list.

This document defines the required workflow for adding an unknown DVR/NVR model, firmware generation, filesystem, container, or stream variant.

## 1. Preserve the source first

Before reverse engineering a new recorder:

1. record device identity and SMART metadata when available;
2. verify hardware/software read-only state;
3. capture an image or bounded research acquisition with GNU ddrescue and a map file;
4. record acquisition parameters in the case audit log;
5. hash the acquired research artifact;
6. never run repair/fsck/chkdsk against the evidence source.

The parser must be developed against a copy/image, not by experimentally writing to the original DVR disk.

## 2. Triage without assumptions

Run the generic layers before choosing a proprietary parser:

```bash
vidrensic source inspect evidence.raw --json
vidrensic profile storage evidence.raw --out storage.json
vidrensic profile source evidence.raw --out samples.json
vidrensic formats detect evidence.raw --json
```

Collect evidence for:

- MBR/GPT/unpartitioned layout;
- EXT/XFS/JFS/FAT/NTFS/exFAT/Btrfs/HFS+ regions;
- WFS/HIK/DHAV/PS or other known structural markers;
- Annex-B H.264/H.265 parameter sets;
- recurring block sizes/alignment residues;
- timestamp-like fields;
- channel identifiers;
- frame/record lengths and footer/back-pointer structures;
- circular wrap behavior;
- index/data separation.

A filename extension, vendor name, or one ASCII string is never sufficient proof.

## 3. Create a research fingerprint

For each new sample, record a small reproducible fingerprint that does not require distributing customer evidence:

```text
source size
sector sizes
partition map
sample offsets
sample SHA-256 values
known signature counts
candidate record-header offsets
candidate block/alignment sizes
codec parameter-set hashes
observed channel range
native timestamp examples
```

Where confidentiality permits, retain synthetic/minimized byte fixtures that reproduce the structure without retaining private surveillance content.

## 4. Separate family from variant

Model the device as layers:

```text
Device / retail model
    ↓
Firmware variant
    ↓
Storage family
    ↓
Index / allocation family
    ↓
Record or container family
    ↓
Codec + timestamp variant
```

Examples of why this matters:

- two retail brands can share the same OEM filesystem;
- one vendor can change storage format between firmware generations;
- `.dav` can describe structurally different containers;
- H.264/H.265 payload can survive even when the proprietary index is lost;
- a channel slot may not represent the same physical camera across recording intervals.

## 5. Add a data-only VariantProfile first

Before writing a new parser, add a JSON-compatible variant profile containing only observed facts:

```json
{
  "profile_id": "example-family-model-generation",
  "family_id": "example-family",
  "variant": "Observed generation",
  "vendor_patterns": ["example*"],
  "model_patterns": ["model-*"],
  "firmware_patterns": ["v5.*"],
  "parameters": {
    "record_alignment": 4096,
    "header_magic": "..."
  },
  "validation_state": "research"
}
```

Profiles are data, not executable code. A profile pack cannot install Python or shell hooks.

## 6. Detection stage

A DETECT implementation must:

- bound all reads;
- reject impossible lengths/offsets;
- combine multiple independent signals where possible;
- expose reasons and confidence;
- avoid vendor certainty when the same family is used by OEM devices;
- produce negative tests demonstrating that common unrelated data does not trigger high confidence.

Vidrensic blocks automatic format selection when confidence is low or the top two format scores are too close.

## 7. Profile stage

A PROFILE implementation may extract metadata hypotheses such as:

- master/superblock candidates;
- video-area boundaries;
- block geometry;
- index locations;
- channel ranges;
- timestamp epochs/packing;
- circular-buffer boundaries.

PROFILE does not imply a recording can be recovered.

## 8. Parse stage

A PARSE implementation must have hard limits for every attacker/corruption-controlled value:

- record sizes;
- extension/header lengths;
- block counts;
- table entry counts;
- recursion depth;
- allocation/index offsets;
- carry buffers;
- decompression/output sizes where applicable.

Malformed structures must become explicit parse errors or REVIEW evidence. The parser must never scan arbitrarily past the evidence bounds because a damaged length field requested it.

## 9. Reconstruction stage

RECONSTRUCT requires independent evidence that output units belong together. Depending on the family this may include:

- allocation/index references;
- record continuation structure;
- footer/back-pointer consistency;
- timestamps;
- channel IDs;
- frame numbers;
- physical proximity as a **soft** signal;
- codec parameter-set/GOP continuity;
- decoder evidence;
- global fragment mutual exclusion.

Physical proximity alone is not enough for a forensic reconstruction when multiple candidate continuations exist.

## 10. Failure-mode corpus

Every supported family should test the failure modes applicable to its storage design:

- missing/corrupt index;
- deleted/unindexed recording;
- partial overwrite;
- circular wrap;
- multi-camera interleaving;
- channel-slot drift;
- fragmented chains;
- bad-sector gaps;
- truncated records;
- corrupt length fields;
- wrong/missing timestamps;
- duplicate records;
- frame-number gaps/resets;
- damaged GOP/parameter sets;
- wrong FPS/duration;
- broken container seek/index;
- mixed codec/firmware variants.

A feature is not considered robust because it works on one clean image.

## 11. Validation levels

Suggested `validation_state` progression:

```text
research
  ↓
synthetic-tested
  ↓
implementation-tested
  ↓
case-validated
  ↓
corpus-validated
```

Promotion should record:

- tool version/commit;
- fixture/source identifier;
- expected discovery counts;
- expected offsets/timestamps/channels;
- expected output hashes when deterministic;
- known ambiguity/failure states;
- independent playback/decode verification where applicable.

## 12. Unknown model fallback

When no proprietary plugin is validated, Vidrensic should still provide useful forensic work without pretending it knows the filesystem:

```text
source safety + SMART
partition/storage map
bounded signature profiler
ranked family detection
Annex-B / MPEG-PS stream evidence
physical hit maps
hashes
exportable research profile
```

This is the foundation for a future **Profiler Package** workflow: an examiner can provide a compact structural profile/minimized sample instead of copying a multi-terabyte case image to development.

## 13. Commercial support rule

A device/model should only appear in a customer-facing supported-model database when a concrete variant profile is tied to a validated family implementation. The database should show the highest real capability:

```text
Detected only
Profiled
Parsed
Recoverable
Validated
Export-supported
```

This prevents a model from being advertised as “supported” when only its disk signature is recognized.
