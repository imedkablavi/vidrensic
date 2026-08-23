# Social preview release checklist

The repository already contains reusable vector identity assets (`docs/assets/vidrensic-mark.svg` and `docs/assets/vidrensic-hero.svg`). The GitHub repository social-preview image itself is a repository setting and is not changed by source commits.

## Preview content

A public preview should use only claims supported by the repository:

- product name: **Vidrensic**;
- short descriptor: **Forensic-first DVR/NVR evidence reconstruction**;
- three factual concepts rather than compatibility counts: **Acquire · Reconstruct · Validate**;
- visual language consistent with the existing mark/hero;
- no vendor logos, recorder-family counts, “certified”, “court-ready”, “universal recovery”, or success-rate claims without published validation evidence.

## Rendering requirements

Before upload, export a raster social card at the dimensions currently recommended by GitHub and inspect the actual repository-card rendering on desktop/mobile. Keep important text away from crop-sensitive edges. The final raster file should be reviewed for contrast and legibility before it is uploaded in repository settings.

## Release check

The preview is considered complete only when an owner/maintainer has uploaded the reviewed raster through GitHub repository settings and visually inspected the rendered card. Committing an SVG to `docs/assets/` alone does not prove the social preview is active.

The current connector used by the forensic release audit can change repository files/branches/PRs but does not expose the repository social-preview setting, so this remains an explicit manual public-release gate rather than a falsely completed item.
