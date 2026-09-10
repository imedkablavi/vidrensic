# Safe Derived-File Deletion

Vidrensic treats deletion as a destructive workspace operation, not as evidence recovery.

## Plan first

Create a plan with:

```text
vidrensic-review deletion-plan \
  --case <case> \
  --path <case>/derived/review/proxy.mp4 \
  --reason "discarded review proxy" \
  --out <case>/work/deletion-plan.json
```

Creating a plan deletes nothing. Every target is recorded with its normalized case-relative path, byte size, SHA-256, safety-root kind and reason.

Only files below the case `derived/` or `work/` roots can be targets. Evidence, acquisitions, reports, logs and state databases are outside the deletion boundary.

## Execute explicitly

Execution requires an explicit `--execute` flag:

```text
vidrensic-review execute-deletion \
  --case <case> \
  --plan <case>/work/deletion-plan.json \
  --execute
```

Before any deletion the full plan is preflighted. Each target must still be a regular non-symlink file inside the same case, its normalized path must match the plan, and its current SHA-256 and size must match the recorded identity. A plan cannot delete itself, and the tombstone log cannot overlap a target.

The implementation rechecks each target immediately before unlinking. A mismatch stops execution; it does not silently fall back to deleting by path alone.

## Tombstones and audit

Successful deletions append a tombstone to `state/deletion_tombstones.jsonl` containing the plan ID, target ID, path, expected and observed SHA-256, size, actor, reason and UTC timestamp. The tombstone file is created with owner-only permissions and opened without following symlinks.

The CLI also appends review deletion-plan creation/execution events to the case hash-chained audit log.

## Important boundary

This workflow is for derived/workspace cleanup only. It is not a secure-wipe implementation and does not attempt to sanitize previously allocated disk blocks. Deletion must never be used as evidence disposal; it only manages mutable case derivatives.
