# Public-release security gates

Before Vidrensic is made public or a public alpha tag is promoted, the default branch should pass all applicable automated checks:

1. **Dependency audit** — install the project in a clean Python 3.12 environment and run `pip-audit` against installed dependencies.
2. **Tracked-public hygiene** — scan tracked public text for common credential formats and suspicious local evidence paths, and reject tracked case/evidence artifacts unless an exact path is explicitly reviewed and allowlisted.
3. **Full-history secret scan** — checkout complete Git history and run pinned Gitleaks with redacted output.
4. **Immutable Actions policy** — reject external GitHub Actions that are not pinned to full commit SHAs.
5. **CodeQL** — run the Python `security-extended` static-analysis suite on pull requests/main and on its configured schedule.
6. **Normal CI** — Python 3.11/3.12/3.13 tests, forensic-critical coverage gate, lint/compile, package build, installed-wheel smoke tests, validation corpus and release-SBOM smoke generation.
7. **Scheduled adversarial regression** — run deterministic malformed-input cases across WFS, DHAV, Annex-B salvage and Hikvision parser boundaries with multiple fixed seeds, bounded input sizes, bounded salvage enumeration and a JSON evidence artifact.

The scheduled adversarial job intentionally has finite case/input bounds and a workflow timeout. Unexpected exceptions or violated parser invariants fail the job rather than being converted into an expected parser error.

This scheduled job is **deterministic adversarial regression**, not coverage-guided fuzzing. Passing it means only that the exercised synthetic inputs remained inside declared parser/error invariants; it does not prove memory safety, absence of vulnerabilities, or real-recorder compatibility.

Passing these gates also does not prove that a repository contains no sensitive information. They are automated controls in addition to owner review of repository history, issue content, attachments, release artifacts, repository settings and licensing before a stable release.
