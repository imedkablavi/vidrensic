# Vidrensic Forensic Release-Readiness Validation Report

**Audit date:** 2026-08-24  
**Repository:** `imedkablavi/vidrensic`  
**Base audited:** `main` at `538001e86b5645d314da08595e3f5b4308ccfdb7`  
**Audit branch:** `audit/forensic-release-readiness-2026-08`  
**Pull request:** #17  
**Product version in package metadata:** `0.6.0a0`

## Executive result

**Stable forensic release readiness: NOT ESTABLISHED.**

This audit strengthens release gates and adds conservative recovery/validation primitives, but it does not create evidence that does not exist. The repository still has **zero admitted real-recorder fixtures** in the versioned real-recorder corpus index. Consequently, this report does not promote WFS, DHAV or Hikvision to broad real-recorder validation and does not claim independent certification.

The appropriate product state remains alpha/development with explicit review boundaries.

## Status legend

- **IMPLEMENTED** — code/test/documentation change exists in this audit branch; automated checks still govern correctness for the final PR head.
- **PARTIAL** — useful bounded capability exists, but a required validation/integration layer is missing.
- **BLOCKED** — promotion requires evidence or infrastructure not present and must not be replaced with a synthetic claim.
- **MANUAL GATE** — source changes alone cannot prove completion.

## Priority-by-priority findings

| Priority | Audit status | Evidence / exact boundary |
|---|---|---|
| Versioned real-recorder corpus | **IMPLEMENTED, EMPTY BY DESIGN** | `validation_corpus/real/real-corpus-index.json` is versioned and currently contains zero cases. Admission tooling requires SHA-256, recorder/firmware identity, acquisition metadata, legal basis/privacy review and independent ground-truth expectations. A zero-case index proves no recorder compatibility. |
| WFS frame/NAL/GOP partial-overwrite salvage | **PARTIAL** | Added bounded Annex-B NAL salvage that emits only units with observed start and end delimiters, discards the final unbounded tail and labels codec/NAL/GOP semantics only when parameter-set evidence is high-confidence. It is not yet wired into automatic WFS recovery and has no real-recorder ground truth; therefore frame/GOP partial-overwrite recovery remains incomplete. |
| Solver performance / branch-and-bound | **PARTIAL / REFERENCE ONLY** | Added a separate reference branch-and-bound selector, equivalence tests against the current production selector and deterministic profiling JSON. Production recovery still uses the existing bounded selector. A truncated B&B run is not an optimum claim, and timing is not a performance guarantee. |
| DHAV circular-wrap chronology | **PARTIAL** | Added a conservative single-wrap assessment: one backward timestamp jump may nominate a candidate pivot only when rotated observed timestamps become monotonic. It never returns PASS and does not reorder source evidence. Multiple jumps remain REVIEW. No real DHAV circular-buffer fixture validates recorder semantics. |
| DHAV audio validation | **PARTIAL** | Added declared audio-metadata assessment for sample rate/channel count/codec codes. This explicitly does not claim audio payload decode correctness, synchronization or codec support. |
| Hikvision parser progression | **GATED / BLOCKED** | Added a regression gate that keeps Hikvision at `PROFILE` while the real-recorder corpus has no Hikvision fixtures. No HIKBTREE/data-block recovery claim is added. Parser promotion requires admitted real fixtures for the exact layouts. |
| E01 / Ex01 / AFF4 | **STRATEGY ONLY** | Added a read-only adapter contract, fail-closed rules and fixture qualification plan. No adapter implementation or support claim is present. Missing segments/objects or integrity failures must stop logical reading rather than fall back to raw-container bytes. |
| Malformed/adversarial input tests | **IMPLEMENTED** | Expanded deterministic malformed-input tests for oversized WFS packet lengths, implausible DHAV lengths, Annex-B start-code storms, bounded salvage enumeration and randomized mutation ranges. These are regression tests, not a proof of parser vulnerability absence. |
| Acquisition/hash/provenance failure recovery | **PARTIAL** | Added tests for source-identity change refusal and atomic acquisition-receipt failure behavior, plus a recovery procedure. Existing source fingerprinting can detect a changed evidence identity. Known gap: ddrescue resume does not yet automatically persist/require a prior fingerprint sidecar on every resume. |
| Installer/package/release qualification | **PARTIAL** | CI validates Python 3.11–3.13 on Linux; release workflow now runs source tests, corpus/index gates, solver equivalence profile, builds sdist/wheel, runs `twine check`, installs the wheel, reruns the synthetic corpus, records qualification reports and verifies SHA-256 sums before upload. No native OS installer is qualified by this audit. |
| Social preview | **MANUAL GATE** | Existing vector brand assets were reviewed and a claim-safe preview checklist was added. The GitHub social-preview setting is not exposed by the connected repository tool, so activation/rendering is not falsely reported as complete. |
| Public demo | **IMPLEMENTED / SYNTHETIC** | Demo documentation now separates the deterministic DHAV demo from the public validation corpus and narrows exactly what each proves. It remains synthetic and cannot establish real-recorder compatibility. |
| Licensing strategy | **REVIEWED, UNCHANGED** | Current bespoke proprietary license remains untouched. `docs/LICENSING_STRATEGY.md` documents proprietary, permissive, copyleft and dual-license tradeoffs, including contributor-rights and fixture/data-license separation. |
| PASS semantics | **IMPLEMENTED** | `docs/RELEASE_QUALIFICATION.md`, the real-corpus admission documentation and this report distinguish CI PASS, public synthetic-corpus PASS, metadata-admission PASS and future real-fixture PASS. |

## What PASS means

### CI PASS

A CI PASS means the declared workflow checks completed successfully for the exact commit and runner matrix represented by that workflow. It establishes neither universal compatibility nor external certification.

### Public validation-corpus PASS

A public corpus PASS means only that the declared expectations for the exact **synthetic** fixtures passed and that the corpus runner performed its configured integrity checks. It is not a real-recorder validation result.

### Real-recorder index validation PASS

The index validator can PASS with zero cases. That means the index is structurally valid; it does **not** mean any recorder family passed validation.

### Future real-recorder fixture PASS

A real fixture PASS would be scoped to the exact source SHA-256, fixture version, recorder/firmware metadata, documented legal provenance, ground-truth method, expectations/tolerances and Vidrensic commit. It would not automatically generalize to another model or firmware.

### Reconstruction candidate status

Successful parsing, native extraction, codec identification or a monotonic chronology hypothesis does not by itself justify `PASS`. Ambiguous, incomplete, bounded/truncated or unvalidated evidence remains `REVIEW` or `UNKNOWN`; structural contradictions may produce `FAIL`.

## What PASS does not prove

No PASS described in this project proves all of the following:

- universal DVR/NVR support;
- correctness on unrepresented firmware or OEM variants;
- zero false positives or false negatives;
- absence of malformed-input/security defects;
- deleted/overwritten media recovery beyond the tested condition;
- correct audio playback/synchronization unless separately validated;
- evidentiary admissibility in any jurisdiction;
- chain-of-custody compliance outside the recorded software operations;
- independent laboratory certification;
- that an analyst selected the correct evidence source, geometry, timezone or case interpretation.

## Forensic fail-closed checks preserved or strengthened

- Evidence file/block-device access remains read-only by default.
- WFS global-search truncation remains review evidence rather than an optimum claim.
- WFS salvage discards unbounded tails instead of inventing end offsets.
- Hikvision is not promoted without real fixtures.
- Container adapter strategy forbids treating unsupported E01/Ex01/AFF4 bytes as a raw disk fallback.
- Source identity change can stop a resume decision.
- Receipt serialization failure cannot leave a final success-looking receipt.
- Release artifacts are not uploaded by the revised release workflow until source/package qualification steps pass.

## Release blockers remaining

1. **No admitted real-recorder corpus cases.** This is the primary blocker for broad recorder-family validation claims.
2. **WFS partial-overwrite salvage is not recorder-integrated/validated.** The new bounded Annex-B primitive is groundwork, not completion.
3. **DHAV circular chronology/audio payload semantics lack real fixtures.** The added assessments deliberately remain hypotheses/review evidence.
4. **Hikvision remains PROFILE only.** No HIKBTREE/data-block promotion until real fixtures exist.
5. **E01/Ex01/AFF4 adapters are not implemented/qualified.**
6. **Acquisition resume fingerprint binding is not automatic end-to-end.**
7. **No native installer qualification.** Current automated qualification covers Python package artifacts on Linux.
8. **No published independent lab rerun.**
9. **Social-preview upload/render verification remains manual.**

## Automated workflow evidence during this audit

The audit intentionally treated workflow failures as evidence rather than hiding them. An early PR run failed Ruff on an explicit `zip(..., strict=...)` rule; that source issue was corrected. A subsequent run passed Ruff/compile but exposed a pytest collection failure because repository-local validation scripts were not importable as a package; `scripts/__init__.py` was added to correct the source-tree test setup.

The authoritative final automated result is the GitHub Actions status attached to the final PR head. This report must not be read as substituting for those checks if the final head is red or incomplete.

## Licensing finding

The current license is proprietary and source visibility does not make Vidrensic open source. Staying proprietary preserves greater owner control but reduces default reuse/contribution rights and third-party packaging adoption. Permissive open source maximizes adoption but grants broad reuse rights; copyleft changes downstream sharing obligations but does not prohibit commercial competition; dual licensing can combine community distribution with commercial terms but requires clean contributor rights. No license change was made by this audit.

## Final audit disposition

The PR is a **release-readiness hardening change**, not a declaration that Vidrensic is forensic-release ready. Merge should require green CI/Security checks and review of the explicit blockers above. A future stable release should remain blocked until the project's intended support claims are backed by legally usable real-recorder fixtures and appropriate independent validation.
