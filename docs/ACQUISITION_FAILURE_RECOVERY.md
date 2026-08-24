# Acquisition / hash / provenance failure recovery

This procedure describes recovery from interrupted or failed acquisition operations. It is not a claim that a damaged source was fully acquired.

## Existing guarantees

Vidrensic uses GNU ddrescue map files for resumable acquisition, checks source safety immediately before execution, verifies requested geometry, writes acquisition receipts atomically through a temporary `.partial` path, and binds new ddrescue state to a persisted source-identity sidecar before ddrescue starts.

The source sidecar is stored next to the map as `<mapfile>.source.json` with owner-only file permissions. It records the source fingerprint plus output/map paths and requested acquisition geometry. Source-binding reads are byte/depth/node/string bounded and reject symlinks so corrupted or redirected local state cannot be silently followed during resume or verification.

For regular image files the automatic binding adds a bounded first/last edge-sample SHA-256 to inode/mtime/size metadata. For block devices Vidrensic prefers OS-reported WWN, then serial, when available. If neither stable hardware identifier is exposed, the sidecar explicitly records the weaker `device-node-fallback` identity level rather than pretending it is strong hardware identity.

For a permitted ddrescue execution Vidrensic also resolves `ddrescue` once, canonicalizes the executable path, records its SHA-256/stat identity and bounded version output, and uses that same absolute path for every pass in the session. The executable is rechecked immediately before and after each pass. A replacement or byte change fails closed rather than silently allowing a later pass to use different observed tool bytes.

Each accepted execution session appends to `<mapfile>.tool-audit.jsonl`. This owner-only JSONL log uses the normal Vidrensic audit hash chain and records the observed executable path/version/SHA-256 plus pass return codes. It is created only after source binding has been accepted, so a blocked legacy-adoption attempt does not look like an executed ddrescue session.

Both acquisition provenance sidecars are ignored by Git by default, and the public-release hygiene gate rejects them even if someone force-adds them. They can contain source paths, device identity, acquisition geometry, host/process metadata and native-tool identity and therefore are not public demo artifacts.

## Acquisition receipt `COMPLETE` semantics

`vidrensic acquire verify` does not treat a complete-looking ddrescue map as sufficient provenance by itself. A receipt can reach `COMPLETE` only when all of the following hold for the verification attempt:

1. the supplied ddrescue return-code list is non-empty and all codes are zero;
2. the map shows the full requested source range as finished;
3. the acquisition output is at least the requested logical size;
4. output hashing was not skipped;
5. `<mapfile>.source.json` exists as a non-symlink, bounded/valid sidecar, is in a confirmed state, matches the output/map paths and requested acquisition geometry, and its persisted source fingerprint matches the source observed during verification;
6. `<mapfile>.tool-audit.jsonl` exists as a non-symlink, stays within the verification size bound, its hash chain verifies, and its final nonblank record is `ddrescue.session.finished`;
7. the final finished tool-audit record explicitly reports `all_zero=true` and its return-code list exactly matches the return-code list supplied to receipt verification; and
8. neither provenance sidecar changes while the receipt verification is reading/hashing it.

Requiring the final audit record matters: an older successful session cannot be reused to obtain `COMPLETE` if a newer `ddrescue.session.started` or `ddrescue.pass.finished` record exists without a terminal session record. An interrupted or still-running newer session therefore remains `REVIEW`.

The receipt stores hashes and selected state for both provenance sidecars so the JSON receipt is bound to their exact bytes at verification time. Missing legacy sidecars, malformed provenance, a changed source, a failed/latest incomplete execution session, or return-code disagreement keeps the receipt in `REVIEW`; Vidrensic does not invent replacement provenance to manufacture `COMPLETE`.

A `COMPLETE` receipt is still scoped evidence, not a statement that the physical source was independently full-hashed before acquisition, that the tool binary is vendor-authentic, that the examiner's host is trustworthy, or that legal chain of custody is established.

## Required resume procedure

1. Preserve the existing ddrescue map, source-binding sidecar, tool-audit sidecar and partial output. Do not delete or rewrite them merely to make the next run look clean.
2. Reinspect the evidence source. Vidrensic compares the current fingerprint with the persisted source binding before ddrescue is allowed to reuse the map.
3. If source identity changed, stop. Do not resume against a different disk/image even when its size is identical.
4. Re-run destination-capacity checks using the current partial-output size.
5. Resume using the same map file, output path and explicit acquisition geometry. A changed output path or range is rejected against the source binding.
6. Vidrensic resolves the currently available ddrescue executable once for the new execution session, records its identity, and executes that absolute path. A different tool identity across separate sessions remains visible in the append-only tool audit rather than being hidden.
7. After ddrescue returns, parse the map against the requested range. Any unresolved/non-finished range keeps the result in review.
8. Hash the resulting image and map unless an explicit policy says otherwise. A skipped or failed output hash does not establish a complete verified acquisition.
9. Generate the receipt against the preserved source binding and tool audit. Any provenance mismatch remains `REVIEW`.
10. Write a new receipt only after all available state has been evaluated. A receipt serialization failure must not leave a final success-looking JSON file.

## Legacy acquisition state without a binding

Existing map/output state created before source-binding support is not silently adopted.

On first encounter Vidrensic:

1. fingerprints the currently supplied source;
2. writes a sidecar with state `pending-legacy-adoption`;
3. **does not execute ddrescue**;
4. tells the examiner to inspect source/provenance and explicitly confirm the sidecar.

After verifying the source, confirm it with:

```bash
python -m vidrensic.acquisition.binding confirm /path/to/image.map.source.json
```

If the source is now exposed under a different path but retains the same validated hardware identity, supply it explicitly:

```bash
python -m vidrensic.acquisition.binding confirm \
  /path/to/image.map.source.json \
  --source /dev/current-device
```

Confirmation re-fingerprints the source and refuses a mismatch. It changes only the binding state; it does not modify the evidence source, map or image bytes. A subsequent normal `vidrensic acquire run ...` performs the usual safety checks and binding comparison again before ddrescue starts.

Legacy output/map state that predates tool-audit support can still be inspected and verified, but it cannot receive a modern `COMPLETE` receipt merely because the map looks finished. Missing execution provenance remains an explicit `REVIEW` reason.

## Failure classes

### Source identity mismatch

**Action:** fail closed. Preserve the old map/output/binding and investigate why the source changed. Do not silently bind the old map to the new source.

### Weak block-device identity

If neither WWN nor serial is exposed, the binding records `device-node-fallback`. This still detects changes to observed geometry/device-node metadata but is weaker across reboot or device re-enumeration. For high-assurance acquisition, record independent device identity (for example photographed labels/serial information and SMART/device metadata where available) in the case notes and avoid treating fallback identity as equivalent to a WWN-backed binding.

### Pending legacy adoption

**Action:** ddrescue remains blocked. Verify provenance and run the explicit binding confirmation command. Do not bypass the pending state by deleting the sidecar and repeatedly retrying.

### Missing or invalid provenance sidecar during receipt verification

**Action:** receipt status remains `REVIEW`. Preserve the existing files and investigate the missing/tampered state. Do not recreate a source binding or tool audit after the fact solely to obtain `COMPLETE`.

### Newer incomplete ddrescue session

**Action:** receipt status remains `REVIEW`. If the final tool-audit record is a new session start or pass record without a matching terminal session record, investigate whether acquisition was interrupted or is still in progress. Do not reuse an older successful session as the current provenance result.

### ddrescue executable identity change during a session

**Action:** fail closed. Preserve the map/output and tool-audit log. Determine whether the executable was upgraded, replaced or modified. Do not silently continue a retry pass using different observed executable bytes. Start a new controlled acquisition session only after the tool change has been reviewed and documented.

The executable SHA-256 identifies observed bytes; it does not prove those bytes are an authentic GNU package. Package-manager provenance, distribution signatures and independent tool qualification remain separate controls.

### ddrescue non-zero return

**Action:** preserve map/output/binding/tool audit, record the return code, inspect map state and decide whether a controlled resume is appropriate. A non-zero pass is not converted to `COMPLETE` merely because output bytes exist.

### Unresolved map ranges

**Action:** status remains review/incomplete. Bad-sector, non-tried, non-trimmed and non-scraped ranges must remain visible.

### Output shorter than requested geometry

**Action:** review/failure condition. Do not pad it and call the acquisition complete unless a separate container format explicitly defines sparse ranges and that behavior is recorded.

### Hash skipped or hash operation failure

**Action:** verification is incomplete. Keep the bytes, record the reason, and retry hashing from the preserved output when operationally safe. Never invent a digest or reuse one from a different file.

### Receipt write failure

**Action:** no final receipt should exist. Preserve acquisition bytes/map/binding/tool audit, correct the destination failure and rerun receipt generation. An old `.partial` receipt blocks overwrite so an examiner must inspect it deliberately.

## Claim boundary

The source-binding sidecar prevents Vidrensic from silently resuming when its persisted source identity does not match the current observation. The tool audit binds each Vidrensic execution session to an observed ddrescue path/version/hash and detects ordinary replacement during that session. A schema-v2 `COMPLETE` acquisition receipt additionally requires those provenance records to be present, valid and mutually consistent with the current source, plan and recorded return codes. None of these mechanisms is a digital signature, trusted timestamp, hardware write blocker, proof of an OS-reported serial/WWN, proof of GNU package authenticity, independent full-source hash, or complete chain-of-custody evidence. Stable-release procedure still requires normal examiner documentation and independent evidence-handling/tool-validation controls.
