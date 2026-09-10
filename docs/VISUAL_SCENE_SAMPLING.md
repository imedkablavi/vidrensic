# Visual scene sampling

`vidrensic-scenes <artifact> --out <sheet.png>` creates a bounded derived contact sheet for fast visual triage of recovered video.

The default is 24 approximately even samples, laid out in a deterministic grid. Sample count is bounded to 256 and thumbnail width to 640 pixels. PNG and JPEG output are supported.

## Forensic boundary

The contact sheet is a **derived review aid**, not evidence and not a replacement for frame-accurate timeline analysis. The manifest records the source SHA-256/SHA-512, output SHA-256/SHA-512, requested sample count, grid, and approximate sampling interval.

The operation hashes the source before and after rendering. If the source changes during rendering, the derived output is removed and the operation fails closed.

Existing outputs and symlink sources/targets are rejected. Derived images are written with owner-only permissions.

## Example

```text
vidrensic-scenes recovered.mp4 --out contact-sheet.png
```

Machine-readable report:

```text
vidrensic-scenes recovered.mp4 --out contact-sheet.png --json
```

Higher density:

```text
vidrensic-scenes recovered.mp4 --out contact-sheet.jpg --samples 48 --thumb-width 320
```

The contact sheet should be used to identify visually interesting regions for subsequent frame/timestamp investigation, bookmarks, or manual review. It does not establish exact frame identity or prove that unsampled intervals are visually uneventful.
