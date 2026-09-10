# Vidrensic Brand Guidelines

## Brand idea

**Vidrensic** combines video evidence with forensic reconstruction. The visual system should communicate four traits:

**evidence-first · technical · precise · trustworthy**

Avoid visual language that suggests surveillance entertainment, cyberpunk decoration, or certainty where the software reports uncertainty.

## Core palette

| Role | Color | Hex |
|---|---|---|
| Ink | Deep evidence navy | `#07111C` |
| Graphite | Interface dark | `#0D1B2A` |
| Cyan | Primary signal | `#22D3EE` |
| Sky | Secondary signal | `#38BDF8` |
| Mint | Verified / healthy | `#34D399` |
| Indigo | Analysis / reconstruction | `#6366F1` |
| White | Primary text | `#F8FAFC` |
| Slate | Secondary text | `#94A3B8` |
| Amber | Review / uncertainty | `#F59E0B` |
| Red | Failure / destructive condition | `#EF4444` |

Cyan is the main brand signal. Mint, amber, and red are semantic status colors and should not replace the core brand palette.

## Typography

Preferred UI and document typeface: **Inter**.

Fallback stack:

```text
Inter, Segoe UI, Arial, sans-serif
```

Use a strong weight for `VIDRENSIC`, section headings, and high-value evidence labels. Body copy should remain regular and readable. Do not use decorative typefaces for primary product surfaces.

## Logo system

The primary mark is the shield + `V` + evidence/play symbol used in:

- `docs/assets/vidrensic-mark.svg`
- `docs/assets/vidrensic-wordmark.svg`
- `docs/assets/vidrensic-hero.svg`

The shield represents evidence boundaries, the `V` represents Vidrensic, and the central play/lens motif represents video evidence under examination.

### Clear space

Keep a minimum clear space around the mark equal to approximately 12% of its displayed width. Do not place text, borders, or other icons inside this zone.

### Minimum size

For digital interfaces, keep the standalone mark at or above 24 px. For print, keep it at or above 8 mm unless a production process has been specifically tested.

### Do not

- rotate or skew the mark;
- stretch it non-proportionally;
- add unofficial gradients, glows, shadows, or outlines;
- recolor it to imitate another brand;
- place it on a background with insufficient contrast;
- combine it with claims such as `certified`, `court approved`, or `official` unless those claims are independently authorized and true.

## UI language

Primary product labels should be factual and operational:

`PASS` · `REVIEW` · `FAIL` · `UNKNOWN`

Prefer:

> `REVIEW — timestamp anomaly observed`

Over:

> `TAMPERED VIDEO`

The brand should never imply that an anomaly proves intentional manipulation.

## Evidence visualization

Timeline and forensic views should use:

- cyan for primary evidence markers;
- indigo for reconstruction hypotheses and analysis layers;
- mint for validated/healthy state;
- amber for unresolved review conditions;
- red for hard failures or invalidated evidence.

Confidence labels should be textual (`High`, `Moderate`, `Low`) as well as visually distinguished. Never rely on color alone.

## Product voice

Use language that is:

- precise rather than dramatic;
- explicit about scope and limitations;
- confident about observed facts and cautious about interpretation;
- consistent across CLI, reports, documentation, and UI.

Good examples:

> `Decoder error region observed from 1240.0s to 1244.0s.`

> `Frame-rate disagreement requires examiner review.`

> `PASS — required qualification checks completed without unresolved review findings.`

Avoid:

> `100% authentic`

> `AI detected manipulation`

> `Guaranteed recovery`

## Asset ownership

Official logos, wordmarks, and distinctive branded artwork are project assets and are not automatically licensed by the software license. See [`LICENSING.md`](LICENSING.md) and the repository `LICENSE` for usage rights.
