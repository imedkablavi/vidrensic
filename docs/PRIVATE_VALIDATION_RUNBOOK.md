# Private real-recorder validation runbook

This runbook defines the local workflow for validating legally authorized real-recorder fixtures without placing active evidence, private reports or restricted manifests in the public Git repository.

## 1. Keep the evidence outside Git

Store the acquired fixture and its working manifest/report directory outside every Git working tree. The private runner enforces this by default.

Recommended layout:

```text
/srv/vidrensic-private/
  cases/
    lab-wfs-001/
      recorder-image.raw
      corpus.json
      report.json
```

Set filesystem ownership and broader directory permissions according to the lab policy. Vidrensic does not change permissions on the evidence source itself.

## 2. Stage the fixture metadata

Use the existing command to hash the source without copying it:

```bash
vidrensic validate private-case /srv/vidrensic-private/cases/lab-wfs-001/recorder-image.raw \
  --out /srv/vidrensic-private/cases/lab-wfs-001/private-case.json \
  --case-id lab-wfs-001 \
  --family wfs \
  --manufacturer Example \
  --model Recorder-1 \
  --firmware 1.0
```

The result is staging metadata only. It is not a corpus admission and it does not contain the source bytes.

## 3. Establish independent ground truth

Before creating a runnable corpus case, document the known facts outside Vidrensic's result:

- acquisition controls and dates;
- source SHA-256 and storage identity;
- recorder/firmware identity;
- known recording intervals and channels;
- known corruption, deletion or overwrite conditions;
- expected structures, timestamps and tolerated uncertainty;
- reviewer/lab role and independent rerun method;
- legal/retention/redistribution basis.

Ground truth must be established independently of the recovery result. Do not convert a plausible Vidrensic output into an expectation after the fact without independent evidence.

## 4. Build a restricted corpus manifest

Use the normal validation-corpus schema, but keep the manifest beside the private source and mark the case as `public`, `lab` or `restricted`. Do not use `synthetic` for this workflow.

Example:

```json
{
  "schema_version": 1,
  "corpus_id": "lab-wfs-validation-2026-09",
  "description": "Restricted WFS recorder validation corpus.",
  "cases": [
    {
      "case_id": "lab-wfs-001",
      "source": "recorder-image.raw",
      "family": "wfs",
      "provenance": "restricted",
      "redistributable": false,
      "source_sha256": "<64-hex-source-sha256>",
      "expectations": [
        {
          "kind": "format_detect",
          "parameters": {
            "minimum_confidence": 0.6,
            "minimum_margin": 0.15
          },
          "expected": {
            "top_plugin": "wfs",
            "requires_review": false
          }
        }
      ],
      "notes": [
        "Ground truth established independently by the lab.",
        "Report remains restricted to the validation team."
      ]
    }
  ]
}
```

Only add expectations that have an independent basis. Use tolerances or coarse assertions when exact scores, timestamps or frame counts are not stable validation targets.

## 5. Run the private validator

```bash
python scripts/run_private_validation.py \
  /srv/vidrensic-private/cases/lab-wfs-001/corpus.json \
  --out /srv/vidrensic-private/cases/lab-wfs-001/report.json
```

The runner:

1. loads the existing corpus schema;
2. rejects synthetic cases;
3. rejects unsupported provenance values;
4. rejects manifests, fixtures and reports located inside Git working trees by default;
5. runs the same deterministic corpus engine used elsewhere;
6. removes temporary recovery products through the corpus engine's existing lifecycle;
7. writes the machine-readable report with owner-only `0600` permissions and no-overwrite semantics.

A controlled private repository can be used with `--allow-git-paths`, but that override must be an explicit organization decision and must never be used for the public Vidrensic repository.

## 6. Interpret the result conservatively

`PASS` means the declared expectations passed for the exact fixture hash, manifest and Vidrensic version recorded by the report. It does not establish universal vendor/firmware support, evidentiary admissibility, absence of false negatives, or independent certification.

`FAIL` means at least one expectation or source-integrity check did not pass. Preserve the report and investigate the declared condition rather than weakening the expectation to obtain a pass.

`ERROR` is retained at expectation level when the runner could not execute an expectation cleanly.

## 7. Promotion into the public real-recorder index

Do not publish the source bytes. Only promote a case into `validation_corpus/real/real-corpus-index.json` when the documented legal, provenance, ground-truth and release requirements are satisfied.

Restricted source hashes/metadata can still remain outside the public repository when disclosure itself is not permitted. The public index should contain only the minimum metadata necessary for the intended claim and must never be used to imply independent validation that did not occur.

## Safety boundary

Do not commit active CCTV footage, seized evidence, credentials, keys or other non-redistributable samples to this repository. The purpose of the private runner is to make the correct workflow easier while keeping the public project evidence-free.
