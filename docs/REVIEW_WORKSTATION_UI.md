# Review Workstation UI

Vidrensic includes a lightweight local graphical review workstation launched by:

```text
vidrensic-review-ui --case <case>
```

The default listener is loopback-only at `127.0.0.1:8765`. A non-loopback bind requires the explicit `--allow-network` flag.

## Candidate list and filters

The left panel provides REVIEW/KEEP/DISCARD state filters, free-text search across artifact path/kind/note, and UTC date/hour filters based on `ReviewItem.updated_utc`.

The date/hour controls are deliberately described as **review-update time**. Recording wall-clock time is not inferred because it is not part of the current `ReviewItem` contract.

Each candidate has a matrix-selection checkbox. The matrix is limited to four candidates and displays them as candidate slots; it does not assert that a slot is a stable physical camera identity.

## Player and recovery

The player provides HTTP Range-backed browser seeking, ±1s/±5s/±30s navigation, frame stepping, playback speeds from 0.25× through 8×, timeline seeking, and bookmark markers.

When browser playback emits `stalled` or `error`, the workstation retries the same review item up to two times and restores the last known position. The recovery path never rewrites the registered artifact.

## Synchronized matrix

Selected candidates can be opened in a four-slot matrix. Starting playback in one slot aligns the current time of the other slots. This is a comparative review convenience, not evidence that all slots share a physical camera or synchronized clock.

## Contact sheet

The workstation samples twelve evenly spaced timestamps from the selected review media and renders them into an in-browser contact sheet. These cells are **visual triage aids**, not exact forensic frame identifiers and not a replacement for hash-bound timeline evidence.

## Evidence boundaries

Review decisions, notes and bookmarks are persisted through `Case.review` and remain separate from evidence bytes. Timeline and decoder reports presented by the workstation remain hash-bound to the registered artifact.

Media requests are made by review-item ID. The server validates that the artifact is still a regular file inside the case and that its SHA-256 matches the registered review item before serving it.

## Security posture

The workstation is intentionally local-first. It does not expose a network listener unless the operator explicitly opts into a non-loopback bind. Browser origins are checked for same-origin requests, response content is marked `nosniff`, and the UI uses a restrictive same-origin Content Security Policy.

This server is a review-workstation convenience layer, not a hardened internet-facing web server. Do not expose it to untrusted networks.

## Remaining workstation work

The current UI still does not provide forensic deletion plans/tombstones, packaged desktop delivery, or recorder-native wall-clock/camera identity guarantees. Those require additional evidence models rather than UI-only assumptions.
