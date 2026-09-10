# Vidrensic product-facing UX

Vidrensic has two presentation layers:

- **Product UX** for examiners and operators. It should be concise, calm and action-oriented.
- **Technical output** for engineers, automation and audit. JSON, advanced help and forensic reports may expose exact values and diagnostics.

## Product language

Use wording that describes the user-visible outcome:

| Internal state | Product wording |
|---|---|
| operation completed | `Analysis complete` / `Verification complete` / `Recovery complete` |
| source is safe for next operation | `Ready` |
| ambiguity blocks automatic choice | `Review required` |
| a derived artifact was created | `Output ready` |
| a report was written | `Report` / `Receipt` |
| no clear format match | `No clear match` |
| confidence score | `High` / `Moderate` / `Low` unless exact value is requested |

Avoid exposing internal implementation terms in the default path, including solver caps, beam widths, fragment IDs, return-code arrays, parser exception names and raw storage diagnostics. Those details belong in the forensic report, JSON output or advanced command path.

## Safety wording

Forensic uncertainty must never be hidden. Convert internal diagnostics into clear user decisions instead of removing the information entirely.

Examples:

- `automatic format selection blocked` -> `No automatic format decision was made. Review the analysis before recovery.`
- `status=REVIEW` -> `Review required`
- `write-enabled source rejected` -> `This source must be read-only before continuing.`
- `source hash mismatch` -> `Source integrity changed. Validation cannot continue.`

The product layer may simplify language, but it must not turn `REVIEW`, `FAIL` or `UNKNOWN` into a success-looking state.

## Interaction hierarchy

The preferred operator path is:

```text
Analyze
  -> understand the source
  -> select the next safe action
  -> recover or review
  -> validate
  -> export
```

Advanced implementation controls remain available to specialists without cluttering the normal workflow.

## Reference products

The wording model follows established forensic-product patterns: guided workflows for case/evidence setup, centralized review, clear investigation stages, and report generation as a deliberate final action. This mirrors the product presentation patterns described by Magnet Witness, OpenText Forensic and Amped FIVE without copying their UI or branding.
