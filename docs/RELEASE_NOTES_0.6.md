# Vidrensic 0.6 alpha — global WFS reconstruction and validation framework

Vidrensic 0.6 is a validation-focused development milestone. It strengthens WFS reconstruction and QA, but it does **not** promote the project to independently validated forensic software.

## WFS global reconstruction

The WFS engine now includes an experimental path-dependent global mode.

Unlike a context-free fragment graph, WFS continuation validity can depend on the incomplete proprietary record carried from the full preceding path. Global mode therefore:

- enumerates bounded carry/tail-aware path hypotheses per simultaneous start;
- keeps competing branches as explicit evidence;
- jointly selects one hypothesis per start;
- forbids physical-fragment reuse across selected paths;
- maximizes proven continuations before minimizing unresolved/ambiguous evidence and physical gap cost;
- records second-best solution evidence where available;
- marks bounded-search truncation as review evidence instead of claiming an optimum.

The normal CLI defaults to:

```bash
vidrensic recover wfs ... --strategy global
```

`--strategy local` remains available for comparison and backward compatibility.

## WFS correctness fix discovered by QA

New reconstruction tests exposed a physical-boundary bug in continuation probing: a look-ahead used for terminal-padding validation could read into the following fragment. Bytes belonging to the next physical fragment could therefore make a legitimate candidate appear invalid.

0.6 caps that evidence read to the candidate fragment boundary. The regression is permanently covered by the WFS reconstruction suite.

## Validation corpus

0.6 introduces `vidrensic validate corpus` and a versioned corpus schema with:

- case IDs;
- fixture family/provenance classification;
- redistributability metadata;
- optional source SHA-256 ground truth;
- deterministic expected operations/results;
- machine-readable expected-vs-actual reports;
- Vidrensic version and UTC run timestamps.

Corpus source paths are confined to the manifest directory. Absolute paths, traversal, symlink sources and source-hash mismatches are rejected.

Current expectation kinds include:

- `source_hash`;
- `format_detect`;
- `wfs_recover`.

The public corpus is intentionally synthetic and validates corpus mechanics. It is **not** presented as a substitute for a broad real-recorder corpus.

## Stronger QA gates

The previous 70% aggregate coverage floor has been replaced with:

- overall coverage >= 80%;
- independent coverage floors for forensic-critical modules;
- validation-corpus execution from the editable build;
- validation-corpus execution again after installing the built wheel.

At this milestone CI reported approximately:

| Area | Coverage |
|---|---:|
| overall | 80.6% |
| WFS local reconstruction | 85.2% |
| WFS path-dependent global reconstruction | 91.1% |
| WFS high-level recovery | 95.0% |
| generic global solver | 91.3% |
| hashing | 90.0% |
| provenance | 91.7% |
| known-key crypto | 84.3% |
| ddrescue orchestration | 100% |

Coverage is a software QA metric, not an independent forensic-validation claim.

## Test expansion

The 0.6 development suite adds direct regression coverage for:

- cross-camera WFS fragment competition;
- branch-specific carry/tail state;
- bounded global-search truncation;
- near-equivalent second-best solutions;
- near-to-far WFS continuation search;
- terminal padding at physical fragment boundaries;
- WFS extraction failure/partial-output handling;
- ddrescue command construction, retry behavior and execution stopping;
- capacity/source geometry failures;
- corpus path traversal, symlink and source-hash controls;
- corpus WFS recovery ground truth;
- installed-wheel validation execution.

## Still incomplete

This milestone does not claim completion of:

- broad multi-device/firmware WFS validation;
- frame/NAL/GOP-level WFS partial-overwrite salvage;
- DHAV circular-wrap chronology and comprehensive audio variants;
- Hikvision HIKBTREE/data-block recovery;
- RAID5/6 parity reconstruction;
- universal recorder encryption/key recovery;
- independent lab certification/validation;
- synchronized graphical review workstation;
- court-ready signed export/report packages.

## Next qualification target

Before a public 0.6 prerelease, the branch must remain green on Python 3.11/3.12/3.13, Security, critical coverage, corpus validation and built-wheel validation. The next major evidence target is a versioned real-recorder fixture corpus with independently established ground truth.
