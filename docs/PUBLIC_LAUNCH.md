# Public Launch Checklist

This file separates engineering readiness from discoverability. A green CI run is necessary but does not by itself make Vidrensic a validated forensic product.

## Repository launch settings

Before making the repository public:

- decide whether the current proprietary/source-visible license is the intended public distribution model;
- verify that no case data, credentials, keys, customer names, internal hostnames, private URLs, or sensitive fixtures exist in Git history;
- choose the final repository name. `vidrensic` is more memorable/searchable than a generic `Video-Forensics` name if the name is legally acceptable;
- set a concise repository description, for example: `Forensic-first DVR/NVR storage reconstruction, triage and CCTV video recovery platform`;
- add repository topics: `digital-forensics`, `video-forensics`, `dvr`, `nvr`, `cctv`, `video-recovery`, `data-recovery`, `wfs`, `dhav`, `h264`, `hevc`, `forensics`, `surveillance`;
- upload the Vidrensic mark/hero as the repository social preview;
- enable Issues; consider Discussions only when there is capacity to moderate/support it;
- configure branch protection/rulesets for `main` and require CI before merge;
- enable Dependabot alerts/updates and secret scanning where available.

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

Create a pre-release such as `v0.5.0-alpha.1` only from a CI-green commit. Release notes should include:

- exact commit SHA;
- Python/platform support;
- live format capability matrix;
- known limitations;
- hashes for distributed wheel/sdist artifacts;
- validation scope and what has **not** been independently validated;
- upgrade notes from the previous alpha.

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

## Launch blockers currently requiring an owner decision

- Repository is currently private.
- License strategy is proprietary/source-visible; changing it is a legal/product decision.
- Repository rename and trademark clearance are owner decisions.
- Social-preview upload and repository topics are GitHub repository settings, not source files.

Everything else in this checklist can be prepared and validated in the development branch before public visibility changes.
