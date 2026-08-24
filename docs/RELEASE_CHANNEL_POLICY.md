# Release channel and tag policy

Vidrensic distinguishes qualification builds from tag publication and prevents a stable tag from being published while the admitted real-recorder corpus is empty.

## Enforced automated policy

`workflow_dispatch` is qualification-only and does not publish a GitHub Release.

For a `v*` tag, `scripts/check_release_tag_policy.py` runs before release build/qualification:

1. the tag must use `v<version>` form;
2. the normalized tag version must exactly match `vidrensic.__version__`;
3. PEP 440 prerelease/dev versions (`a`, `b`, `rc`, `dev`) are treated as prereleases and may qualify while the real-recorder corpus has zero admitted cases;
4. a stable version is blocked when `validation_corpus/real/real-corpus-index.json` has zero cases.

Examples with the current package version `0.6.0a0`:

```bash
python scripts/check_release_tag_policy.py \
  --ref-name v0.6.0a0 \
  --ref-type tag
```

This is an allowed prerelease tag even while the authorized real-recorder corpus is still empty.

A mismatched tag is blocked:

```bash
python scripts/check_release_tag_policy.py \
  --ref-name v0.6.0 \
  --ref-type tag
```

With package version `0.6.0a0`, that command fails because the tag and package version do not match. After the package is intentionally promoted to a stable version, the same policy additionally refuses publication until the real-recorder index contains at least one schema-valid admitted case.

## What the stable gate does not prove

A non-empty real-recorder index is only a minimum automated prerequisite. It does not by itself establish recorder-family support, firmware coverage, legal authorization, independent lab validation, evidentiary admissibility, or readiness for a public stable release.

All manual gates in `docs/RELEASE_QUALIFICATION.md` remain mandatory. In particular, a stable release still requires legally authorized real fixtures, review of the actual fixture results, native-tool provenance review, installer/deployment qualification where claimed, repository security settings, and a real tag run proving the attestation/Sigstore publication path.

Never add synthetic or fabricated entries to the real-recorder index to satisfy this gate.
