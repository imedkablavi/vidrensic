# Review Workstation UI

Vidrensic includes a lightweight local graphical review workstation launched by:

```text
vidrensic-review-ui --case <case>
```

The default listener is loopback-only at `127.0.0.1:8765`. A non-loopback bind requires the explicit `--allow-network` flag.

## Current capabilities

The UI provides a master/detail review layout with:

- review-item search and REVIEW/KEEP/DISCARD filtering;
- sticky video player;
- HTTP Range media delivery for seeking in the browser;
- ±1s, ±5s and ±30s navigation;
- frame-step controls;
- playback speeds from 0.25× through 8×;
- timeline progress and bookmark markers;
- timing/QC badges from the normalized review timeline contract;
- KEEP/REVIEW/DISCARD actions;
- analyst notes;
- timestamp bookmarks.

Media is served by review-item ID rather than an arbitrary filesystem path. Before a media request is served, the server checks the artifact remains a regular file inside the case and verifies its SHA-256 against the registered review item. A changed artifact is rejected from playback.

Mutations are sent to the existing `Case.review` API, preserving the artifact SHA-256 binding and audit trail.

## Timeline discovery

When a normalized review timeline contract is already present in `reports/`, the UI loads it directly. Otherwise the server can build a contract from matching timeline/decoder reports whose SHA-256 matches the review item.

Report discovery is bounded by file count and total bytes. Reports outside the case or symlinked reports are ignored/rejected.

## Security posture

The workstation is intentionally local-first. It does not expose a network listener unless the operator explicitly opts into a non-loopback bind. Browser origins are checked for same-origin requests, response content is marked `nosniff`, and an inline Content Security Policy restricts the UI to same-origin resources.

This server is a review workstation convenience layer, not a hardened internet-facing web server. Do not expose it to untrusted networks.

## Remaining workstation work

The initial UI does not yet provide synchronized multi-camera playback, hour/date filters, deletion plans/tombstones, or a fully packaged desktop application. Those remain separate engineering milestones.
