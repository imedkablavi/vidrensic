# Review Workstation State

Vidrensic keeps analyst review state separate from evidence bytes. Review state is case-local SQLite data stored at `state/review.sqlite3` and is exposed through `Case.review` for the future graphical workstation and the current `vidrensic-review` CLI.

## Review states

- `REVIEW`: candidate still needs analyst review.
- `KEEP`: analyst selected the artifact for retention/review output.
- `DISCARD`: analyst does not want to retain the artifact as a review selection.

Changing state never modifies or deletes the underlying media file.

## Artifact binding

Every review item stores the artifact path and SHA-256. Mutating operations require the expected SHA-256 again. A stale or mismatched digest is rejected, which prevents applying analyst decisions to a replaced artifact at the same path.

Review artifacts must be regular files inside the case root and may not be symlinks. Notes, labels and timestamps are bounded, and timestamps must be finite non-negative values.

## Bookmarks and notes

A bookmark binds to one review item and records a media timestamp, optional label and analyst note. When the registered duration is known, timestamps beyond that duration are rejected.

Item state changes, notes and bookmark creation are appended to the case audit log. The audit log remains the authoritative mutation history; SQLite is the current queryable review state.

## CLI

List items:

```text
vidrensic-review list --case <case> [--state REVIEW|KEEP|DISCARD] [--limit 100] [--json]
```

Set state:

```text
vidrensic-review set-state --case <case> --item <id> --sha256 <sha256> --state KEEP
```

Set a note:

```text
vidrensic-review note --case <case> --item <id> --sha256 <sha256> --text "Primary event"
```

Add a bookmark:

```text
vidrensic-review bookmark --case <case> --item <id> --sha256 <sha256> --time 42.5 --label "entry"
```

The GUI should call the same review API rather than parsing CLI output. Native/recovered media and derived review proxies remain distinct artifacts.

## Explicit limitation

This layer is a state/data contract, not the graphical workstation itself. It does not yet provide the sticky player, synchronized multi-camera matrix, timeline UI, frame stepping controls or visual filtering described in the engineering roadmap.
