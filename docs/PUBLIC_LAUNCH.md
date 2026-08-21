# Public Launch Checklist

This file separates engineering readiness from discoverability. A green CI run is necessary but does not by itself make Vidrensic a validated forensic product.

## Repository launch settings

Current repository state:

- repository name: `vidrensic`;
- visibility: public;
- description set for DVR/NVR forensic recovery;
- public-history secret scan and dependency audit enabled;
- deterministic synthetic demo available;
- first public alpha tag/release created.

Remaining repository-level hardening:

- confirm whether the current proprietary/source-visible license is the intended long-term public distribution model;
- upload/confirm the Vidrensic social preview;
- configure branch protection/rulesets for `main` and require CI + Security before merge;
- keep Dependabot alerts/updates and secret scanning enabled where available;
- optionally enable Discussions once there is capacity to moderate/support them.

Recommended topics: `digital-forensics`, `video-forensics`, `dvr`, `nvr`, `cctv`, `video-recovery`, `data-recovery`, `wfs`, `dhav`, `h264`, `hevc`, `forensics`, `surveillance`.

## Default-branch content

The public default branch should include:

- current README and capability matrix;
- `CITATION.cff` so GitHub surfaces **Cite this repository**;
- license, notice, authorship and security policy;
- contribution guide and code of conduct;
- reproducible synthetic demo;
- format request issue form and safe sample-submission policy;
- validation methodology and explicit unsupported/experimental claims;
- changelog and roadmap.

## First public release

The first pre-release is `v0.5.0-alpha.1`. Release notes should include:

- exact commit SHA;
- Python/platform support;
- live format capability matrix;
- known limitations;
- hashes for distributed wheel/sdist artifacts;
- validation scope and what has **not** been independently validated.

Do not call the release `1.0` until the validation corpus, migration policy, supported family/variant matrix and release qualification criteria are mature enough to defend that claim.

## Launch material

Prepare one clear technical announcement, not marketing spam. It should contain:

1. the problem: proprietary DVR/NVR storage and missing indexes;
2. one 20–40 second terminal demo or screenshot sequence;
3. the differentiator: evidence-first capability levels and preserved ambiguity;
4. the current real format matrix;
5. a request for sanitized lab fixtures / format documentation;
6. a direct link to the reproducible demo and support matrix.

Suitable practitioner audiences include digital-forensics, CCTV/video-forensics, data-recovery and security-research communities where project sharing is allowed. Respect each community's self-promotion rules.

## Metrics worth tracking

Stars are useful as a discovery signal, but track more meaningful indicators too:

- unique cloners / returning visitors;
- demo completions or issue references to it;
- qualified format requests;
- external fixtures contributed;
- pull requests from non-maintainers;
- citations/research references;
- false-positive/false-negative reports;
- number of families promoted through validated capability stages.

## Remaining owner decisions

- long-term license strategy remains a legal/product decision;
- branch ruleset/protection and some GitHub-native security settings are repository settings;
- social-preview presentation and community launch cadence remain owner-controlled launch choices.
