# Security Policy

Vidrensic processes evidence sources, malformed proprietary media, untrusted binary
structures, and external decoder output. Security defects can therefore affect
both host safety and evidentiary integrity.

## Reporting a vulnerability

Do not publish a suspected vulnerability, evidence sample, customer case, or
private recovery profile in a public issue.

Report security concerns privately to the repository owner `@imedkablavi` through
an authorized private channel associated with the GitHub account or organization.

Include, where possible:

- affected Vidrensic version or commit;
- operating system and Python version;
- exact command or workflow;
- minimal reproduction steps;
- whether a crafted file/device can trigger the issue;
- whether evidence can be modified, deleted, misidentified, or exfiltrated;
- crash output with sensitive case data removed.

## Security design rules

- Never invoke external tools through `shell=True`.
- Treat filenames, metadata, device labels, manifests, and plugin output as
  untrusted input.
- Never follow unvalidated paths outside a case root for destructive operations.
- Refuse write-enabled evidence block devices by default.
- Do not mount or repair proprietary evidence filesystems.
- Bound parser lengths before allocation or reads.
- Bound external-process runtime with timeouts where practical.
- Preserve native artifacts before generating derived media.
- Record destructive or evidence-affecting operations in the case audit log.
- Prefer explicit allowlists for supported media suffixes and parser record types.

## Supported versions

During alpha development only the latest `main` release line receives security
fixes. Older alpha commits are development snapshots, not supported forensic
releases.
