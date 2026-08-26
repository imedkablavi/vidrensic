# Licensing strategy review

This document is analysis only. It does **not** change `LICENSE`, copyright ownership, contributor rights or the current proprietary status of Vidrensic.

## Current position

The repository currently uses a bespoke proprietary license. Public visibility of the source does not grant general rights to use, modify or redistribute it. That model maximizes owner control over commercial use, redistribution, competing products and unreleased forensic research, but it creates significant friction for outside adoption and contribution.

## Option 1 - remain proprietary

Advantages:

- strongest control over commercial redistribution and competing products;
- easier to reserve sensitive recorder profiles, customer fixtures and internal validation data;
- straightforward path to negotiated commercial/internal-use licenses;
- no obligation to publish modifications made by licensees unless contracts say otherwise.

Tradeoffs:

- GitHub users cannot safely assume they may run, fork or contribute to the code;
- fewer independent reviewers and downstream packagers are likely to invest effort;
- many organizations avoid source-visible proprietary tools in automated build/distribution systems;
- community contributions require explicit contributor terms so the owner has clear rights to accept and distribute them;
- calling the project “open source” would be inaccurate under the current license.

## Option 2 - permissive open source (Apache-2.0 or MIT)

Advantages:

- lowest adoption friction for users, researchers, integrators and distributors;
- easiest path to third-party packaging, reproducible builds and external testing;
- Apache-2.0 adds an explicit patent grant and termination mechanism that MIT does not spell out in the same detail;
- broad community contribution and independent validation are easier.

Tradeoffs:

- competitors may legally reuse the code within the license terms;
- permissive licensing does not require downstream modifications to remain open;
- proprietary recorder research committed to the repository becomes broadly reusable;
- changing later from already-released permissive versions does not revoke rights already granted to those versions.

## Option 3 - copyleft open source (GPL/AGPL family)

Advantages:

- downstream distribution of covered derivatives generally carries source-sharing obligations;
- AGPL can also address certain network-service use cases;
- may deter closed redistribution more than permissive licenses.

Tradeoffs:

- compatibility analysis with dependencies, plugins and commercial integrations becomes more important;
- some commercial adopters prohibit or heavily review strong-copyleft components;
- copyleft still does not create a prohibition on commercial competition; it changes the conditions under which covered code can be distributed/used.

## Option 4 - dual licensing

A common commercial structure is to publish the same core under an open-source license while also offering a separate commercial license for customers that want different terms.

Advantages:

- community adoption and external validation can coexist with a commercial channel;
- organizations that cannot accept the open-source license can negotiate commercial rights.

Tradeoffs:

- the project must own or have sufficiently broad contributor rights to relicense contributed code;
- contributor agreements/DCO policy must be designed before substantial outside contribution arrives;
- sensitive fixtures and proprietary profiles may still need to live outside the open-source distribution.

## Code license and fixture/data license should be separate decisions

Recorder images, validation corpora, screenshots and vendor documentation can carry different privacy/copyright/redistribution constraints from source code. Even if the application becomes open source, real-recorder fixtures should use explicit per-fixture provenance and redistribution terms. Do not assume the code license automatically grants rights to sample evidence.

## Contributor rights

Before accepting substantial external contributions under any future model, define whether the project uses:

- Developer Certificate of Origin (DCO) sign-off;
- a Contributor License Agreement (CLA);
- direct copyright assignment; or
- ordinary inbound=outbound licensing under the repository license.

The correct choice depends on whether future dual licensing/relicensing is a goal.

## Decision criteria

A future license decision should explicitly rank these goals: commercial control, third-party adoption, independent forensic validation, external packaging, contributor growth, ability to keep recorder research private, and ability to dual-license.

No automatic license change is made by this audit. Any change should be a deliberate owner decision and, for a commercial product, reviewed by qualified legal counsel for the jurisdictions and distribution model involved.
