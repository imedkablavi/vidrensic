## Summary

Describe the forensic/recovery problem and the change.

## Evidence / rationale

What format evidence, specification, fixture, test vector or reproducible observation supports this implementation?

## Testing

- [ ] Added/updated known-good test
- [ ] Added malformed/boundary/regression test where applicable
- [ ] `pytest`
- [ ] `ruff check vidrensic tests`
- [ ] Documentation/support matrix updated if capability changed

## Forensic safety checklist

- [ ] Evidence sources remain read-only by default
- [ ] Parser-controlled offsets/lengths/counts are bounded
- [ ] Existing artifacts are not silently overwritten
- [ ] Ambiguity remains explicit (`REVIEW`/`UNKNOWN`) when unresolved
- [ ] Native and derived data remain distinguishable
- [ ] No cryptographic key bytes, credentials or private evidence are logged
- [ ] No capability claim exceeds what the implementation/tests establish

## Compatibility / limitations

Describe format variants, API/CLI changes, migration concerns and known limitations.
