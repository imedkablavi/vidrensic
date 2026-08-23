# Acquisition / hash / provenance failure recovery

This procedure describes recovery from interrupted or failed acquisition operations. It is not a claim that a damaged source was fully acquired.

## Existing guarantees

Vidrensic uses GNU ddrescue map files for resumable acquisition, checks source safety immediately before execution, verifies requested geometry, writes acquisition receipts atomically through a temporary `.partial` path, and binds new ddrescue state to a persisted source-identity sidecar before ddrescue starts.

The sidecar is stored next to the map as `<mapfile>.source.json` with owner-only file permissions. It records the source fingerprint plus output/map paths and requested acquisition geometry.

For regular image files the automatic binding adds a bounded first/last edge-sample SHA-256 to inode/mtime/size metadata. For block devices Vidrensic prefers OS-reported WWN, then serial, when available. If neither stable hardware identifier is exposed, the sidecar explicitly records the weaker `device-node-fallback` identity level rather than pretending it is strong hardware identity.

## Required resume procedure

1. Preserve the existing ddrescue map, source-binding sidecar and partial output. Do not delete or rewrite them merely to make the next run look clean.
2. Reinspect the evidence source. Vidrensic compares the current fingerprint with the persisted binding before ddrescue is allowed to reuse the map.
3. If source identity changed, stop. Do not resume against a different disk/image even when its size is identical.
4. Re-run destination-capacity checks using the current partial-output size.
5. Resume using the same map file, output path and explicit acquisition geometry. A changed output path or range is rejected against the binding.
6. After ddrescue returns, parse the map against the requested range. Any unresolved/non-finished range keeps the result in review.
7. Hash the resulting image and map unless an explicit policy says otherwise. A skipped or failed output hash does not establish a complete verified acquisition.
8. Write a new receipt only after all available state has been evaluated. A receipt serialization failure must not leave a final success-looking JSON file.

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

## Failure classes

### Source identity mismatch

**Action:** fail closed. Preserve the old map/output/binding and investigate why the source changed. Do not silently bind the old map to the new source.

### Weak block-device identity

If neither WWN nor serial is exposed, the binding records `device-node-fallback`. This still detects changes to observed geometry/device-node metadata but is weaker across reboot or device re-enumeration. For high-assurance acquisition, record independent device identity (for example photographed labels/serial information and SMART/device metadata where available) in the case notes and avoid treating fallback identity as equivalent to a WWN-backed binding.

### Pending legacy adoption

**Action:** ddrescue remains blocked. Verify provenance and run the explicit binding confirmation command. Do not bypass the pending state by deleting the sidecar and repeatedly retrying.

### ddrescue non-zero return

**Action:** preserve map/output/binding, record the return code, inspect map state and decide whether a controlled resume is appropriate. A non-zero pass is not converted to `COMPLETE` merely because output bytes exist.

### Unresolved map ranges

**Action:** status remains review/incomplete. Bad-sector, non-tried, non-trimmed and non-scraped ranges must remain visible.

### Output shorter than requested geometry

**Action:** review/failure condition. Do not pad it and call the acquisition complete unless a separate container format explicitly defines sparse ranges and that behavior is recorded.

### Hash skipped or hash operation failure

**Action:** verification is incomplete. Keep the bytes, record the reason, and retry hashing from the preserved output when operationally safe. Never invent a digest or reuse one from a different file.

### Receipt write failure

**Action:** no final receipt should exist. Preserve acquisition bytes/map/binding, correct the destination failure and rerun receipt generation. An old `.partial` receipt blocks overwrite so an examiner must inspect it deliberately.

## Claim boundary

The source-binding sidecar prevents Vidrensic from silently resuming when its persisted source identity does not match the current observation. It is not a digital signature, trusted timestamp, hardware write blocker, or proof that an OS-reported serial/WWN is authentic. Stable-release procedure still requires normal examiner documentation and independent evidence-handling controls.
