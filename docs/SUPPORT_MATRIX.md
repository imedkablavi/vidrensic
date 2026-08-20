# Vidrensic Support Matrix

This document is the source of truth for **implemented support**, **validation stage**, and **research targets**.

A vendor name is not treated as a filesystem specification. The same brand can ship multiple OEM platforms, filesystems, containers, codecs, timestamp layouts, and firmware variants. Conversely, multiple retail brands can use the same OEM storage family.

## Support-level meanings

| Level | Meaning |
|---|---|
| `NONE` | Known research target only; no product capability is claimed. |
| `DETECT` | Evidence can be recognized with bounded signature/structure checks. |
| `PROFILE` | Structural metadata/hypotheses can be extracted without claiming recording recovery. |
| `PARSE` | Records/containers can be structurally parsed. |
| `RECONSTRUCT` | The engine can rebuild or demultiplex recordings for at least validated variants. |
| `VALIDATE` | Family-specific reconstruction can be tied into full QC and consistency checks. |
| `EXPORT` | Family-specific native/review export semantics and reporting are implemented. |

These levels describe software capability. They do **not** mean an alpha build is independently certified forensic software.

## Implemented format families

| Family | Current level | Topology | Current capability | Important limitation |
|---|---:|---|---|---|
| WFS | `RECONSTRUCT` | Proprietary filesystem / interleaved fragments | Timestamp scan, fragment-chain reconstruction, mutual exclusion, native HEVC extraction | Current parser is validated against the observed project corpus; global graph solver and frame-level overwrite salvage are pending |
| DHAV | `RECONSTRUCT` | Raw interleaved frame stream / DHFS frame layer | Header/footer validation, timestamp/channel/frame metadata, bounded carving, per-channel native + elementary demux | Current output preserves physical order; circular-wrap chronological solving is pending |
| Hikvision proprietary | `PROFILE` | Proprietary filesystem | Dynamic `HIKVISION@HANGZHOU` Master Sector discovery and geometry plausibility analysis | HIKBTREE/data-block recovery is not yet production-supported |
| Annex-B H.264/H.265 | `PARSE` | Elementary stream | NAL/start-code and parameter-set recognition; can be passed to generic media QC/export workflows | No generic wall-clock metadata exists in Annex-B itself |
| MPEG-PS/PES | `PARSE` | Container | Pack/PES recognition for standard and surveillance-derived PS data | Recorder-specific metadata/timestamps require variant profiles |
| EXT/XFS/JFS/FAT/NTFS/exFAT/Btrfs/HFS+ | Storage profiling | Known filesystem | Non-mounting MBR/GPT and superblock identification | Presence of a known filesystem does not imply DVR video is stored as ordinary files |

## Problems the engine is being designed around

| Failure / case condition | WFS | DHAV | Hikvision | Generic media layer | Status / strategy |
|---|---:|---:|---:|---:|---|
| Missing/corrupt recorder index | Yes | Yes | Research | N/A | WFS fragment evidence; DHAV frame carving |
| Deleted/unindexed recordings still present on media | Yes | Yes | Research | N/A | Signature/structure recovery rather than directory undelete |
| Multi-camera interleaving | Yes | Yes | Research | N/A | Mutual exclusion / channel metadata demux |
| Camera slot changes between hours | Preserved as ambiguity | Channel field available | Research | N/A | Never assume slot = physical camera |
| Circular recording wrap | Detect/partial | Detect/partial | Research | N/A | Chronological wrap solver is planned |
| Fragmented recording | Yes, local solver | Frame carving | Research | N/A | Global weighted fragment graph planned |
| Partial overwrite inside a recording | Limited | Valid surviving frames can be identified | Research | Limited | Dedicated frame-level salvage is a future milestone |
| Bad sectors / unstable HDD | Acquisition layer | Acquisition layer | Acquisition layer | Acquisition layer | Read-only + GNU ddrescue map/resume; reconstruction must preserve gaps |
| Truncated proprietary record | REVIEW/stop | Can identify invalid/missing footer | Research | Container dependent | Do not silently invent bytes |
| Wrong duration / wrong FPS | QC detects | QC after media preparation | Future | QC detects | Timing correction must remain a derived operation |
| Broken MP4 seek/index | Generic media QC | Generic media QC | Generic media QC | Yes | ffprobe/full decode/remux workflow; original remains unchanged |
| Damaged GOP / missing VPS/SPS/PPS | Future salvage | Future salvage | Future salvage | Detectable | Parameter-set reconstruction requires separate evidence and audit |
| Timestamp gaps/drift | Evidence preserved | Evidence preserved | Future | Container dependent | Native and corrected timelines must remain separate |
| Audio/video desync | Future | Variant dependent | Future | Media layer | Audio requires explicit per-format timestamp validation |

## Research targets — not yet claimed as supported

The following families/variants are explicitly tracked because they occur in commercial DVR-forensics ecosystems, but Vidrensic must not label them supported until samples and regression fixtures validate the implementation:

- WFH family: WFH 1 / 2 / 3 / 4
- IFS family and known variant names such as IFS, IFS_MM5, IFS_MPEG, IFS_IMM4, IFS_Formatted, IFS_IMM5Nh
- Stream / Stream_db variants
- TangoMagic
- Hikvision HIK/HIKSql variants beyond the current Master Sector profiler
- additional DHFS generations and DHAV extension-header variants
- TDFS, BJPEG, JDAT, Milefs and other recorder-specific families encountered in the field
- OEM/white-label HiSilicon-based recorders where the retail brand does not identify the storage implementation

A research-target name is **not** a parser and is never shown as a recovery-capable family in the CLI capability matrix.

## OEM and model policy

Vidrensic separates these concepts:

```text
Retail brand / recorder model
        ↓
Device / firmware variant profile
        ↓
Storage family
        ↓
Record / container family
        ↓
Codec + timestamp variants
        ↓
Recovery strategies
```

This prevents assumptions such as:

- every device from one vendor uses one filesystem;
- every `.dav` file has the same internal format;
- camera/channel number always maps to the same physical camera;
- a filesystem signature alone proves the recording layout;
- a playable file is automatically a validated forensic reconstruction.

## Promotion rule

A family only moves to a higher support level when all of the following exist:

1. documented structural evidence;
2. bounded parser limits and corruption handling;
3. synthetic positive/negative regression fixtures;
4. at least one real known-good validation source for the variant;
5. expected hashes/record counts/timestamps recorded in the validation corpus;
6. failure-case tests (truncation, malformed lengths, missing metadata, duplicates, wrap/gaps as applicable);
7. clear forensic report semantics for what is native versus derived.

See `FORMAT_ONBOARDING.md` for the workflow used to add new recorder families.
