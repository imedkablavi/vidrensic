# Contributing to Vidrensic

Vidrensic is forensic software. A change that produces plausible output while weakening evidence safety is worse than a visible failure. Contributions are therefore reviewed for correctness, provenance and failure behavior in addition to style.

## Good first contributions

Useful contributions include:

- synthetic or legally shareable format fixtures;
- malformed/corrupted regression cases;
- parser bounds and input validation;
- format/firmware documentation with reproducible evidence;
- unit and integration tests;
- deterministic recovery algorithms;
- CLI usability and documentation improvements;
- performance work that preserves forensic semantics.

Do **not** upload confidential case evidence, credentials, cryptographic keys, personally identifying footage, or material you are not authorized to share.

## Development setup

```bash
git clone https://github.com/imedkablavi/Video-Forensics.git
cd Video-Forensics
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
vidrensic doctor
pytest
ruff check vidrensic tests
```

The supported development matrix is Python 3.11–3.13 on Linux.

## Forensic invariants

Changes should preserve these rules unless the PR explicitly proposes and justifies a policy change:

1. Evidence sources are read-only by default.
2. No filesystem repair is performed on evidence.
3. A signature is evidence, not proof of a complete format match.
4. A parser must bound offsets, lengths and record counts before reading.
5. Recovery ambiguity must remain visible.
6. Native output is separated from review/transcoded output.
7. Native recorder time is never silently replaced by derived/corrected time.
8. Cryptographic key bytes must not appear in logs, receipts or case audit records.
9. Existing artifacts are not silently overwritten.
10. Unsupported operations fail explicitly instead of returning empty/success-looking output.

## Tests required for parser/recovery changes

A parser or recovery PR should normally include:

- at least one known-good fixture/test;
- at least one malformed or boundary case;
- a regression test for the bug/behavior being changed;
- an assertion that the source remains unchanged;
- explicit expected status (`PASS`, `REVIEW`, `FAIL`, `UNKNOWN`) where applicable.

If the algorithm resolves competing hypotheses, include an ambiguity/tie case as well as a clear winner.

## Fixture guidance

Prefer compact synthetic fixtures generated in tests. If real recorder bytes are necessary, minimize them to the smallest legally redistributable range and document:

- recorder/OEM family if known;
- firmware/model if known;
- source offset and sector/fragment assumptions;
- expected structure;
- SHA-256 of the fixture;
- why redistribution is permitted.

## Pull requests

Keep PRs focused. In the description, state:

- the forensic problem;
- what changed;
- what evidence supports the implementation;
- failure modes considered;
- tests added;
- compatibility impact;
- remaining limitations.

Run the full local checks before submitting. GitHub CI is the final automated gate, not a replacement for local reasoning.

## Documentation claims

Do not use words such as **supported**, **validated**, **decrypts**, **recovers** or **forensic-grade** beyond what the implementation and test corpus establish. Capability stages in the code and support matrix are authoritative.

## License

Contributions are accepted under the repository’s existing proprietary license and project ownership terms. Do not submit code that you do not have the right to contribute or code whose license is incompatible with this repository.
