# Public-release security gates

Before Vidrensic is made public or a public alpha tag is promoted, the default branch should pass all of the following automated checks:

1. **Dependency audit** — install the project in a clean Python 3.12 environment and run `pip-audit` against installed dependencies.
2. **Tracked-text hygiene** — scan tracked public text for common credential formats and suspicious local evidence paths.
3. **Full-history secret scan** — checkout complete Git history and run pinned Gitleaks with redacted output.
4. **Normal CI** — Python 3.11/3.12/3.13 tests, coverage gate, lint/compile, package build and installed-wheel smoke tests.

Passing these gates does not prove that a repository contains no sensitive information. It is an automated release control in addition to an owner review of repository history, issue content, attachments, release artifacts and licensing before changing visibility.
