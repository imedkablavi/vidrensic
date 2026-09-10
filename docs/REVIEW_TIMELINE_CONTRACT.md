# Review Timeline Contract

`vidrensic.media.review_timeline.build_review_timeline()` produces the UI-neutral contract consumed by the future graphical review workstation.

## Inputs

The contract is built from one case review item plus a timeline report and, optionally, a decoder-error report. Each report must be a regular non-symlink file inside the same case root.

The report's `hashes.sha256` must exactly match the review item's registered artifact SHA-256. A mismatch is rejected rather than silently mixing observations from different media artifacts.

## Output shape

```text
schema_version
contract
item
media
timeline
decoder_errors
bookmarks
bindings
```

`timeline` contains the existing normalized timing inventory: duration confidence, observed duration, inferred frame rate, keyframes, timing anomaly counters and anomaly records.

`decoder_errors` contains the sampled decoder-region map when one was supplied.

`bookmarks` are the analyst bookmarks already persisted in `ReviewStore`.

`bindings` records the review-item SHA-256 and the source report paths/hashes, with `hash_bound=true`.

## CLI

```text
vidrensic-review timeline \
  --case <case> \
  --item <review-item-id> \
  --timeline-report <timeline.json> \
  [--decoder-report <decoder.json>] \
  --out <review-timeline.json>
```

The output is a derived review artifact. It is not a replacement for the native/recovered media or its forensic reports.

## GUI contract

The graphical workstation should consume this contract for timeline/QC/bookmark display and use `Case.review` for state mutations. It should not parse human-readable CLI output.

The contract intentionally does not decide legal or evidentiary conclusions. `REVIEW`, `KEEP`, `DISCARD`, timing confidence and decoder regions remain analyst-facing evidence signals.
