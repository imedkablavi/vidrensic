from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from vidrensic.plugins.wfs.branch_bound import select_global_hypotheses_branch_bound
from vidrensic.plugins.wfs.global_reconstruct import WFSPathHypothesis, select_global_hypotheses


def _hypotheses(starts: int, options: int) -> dict[int, tuple[WFSPathHypothesis, ...]]:
    result: dict[int, tuple[WFSPathHypothesis, ...]] = {}
    # Every start has one high-quality shared fragment and several unique
    # alternatives. This deterministic shape creates realistic cross-start
    # competition while retaining at least one disjoint solution.
    for index in range(starts):
        start = index + 1
        rows = []
        for choice in range(options):
            shared = 1000 + choice if choice < max(1, options // 2) else 10_000 + index * 100 + choice
            rows.append(
                WFSPathHypothesis(
                    start_fragment=start,
                    fragments=(start, shared, 20_000 + index * 100 + choice),
                    total_cost=float(choice),
                    ambiguous_steps=1,
                    unresolved_steps=0,
                    candidate_counts=(options,),
                    terminal_reason="profile-synthetic",
                )
            )
        result[start] = tuple(rows)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile WFS global hypothesis selectors")
    parser.add_argument("--starts", type=int, default=5)
    parser.add_argument("--options", type=int, default=7)
    parser.add_argument("--max-combinations", type=int, default=250_000)
    parser.add_argument("--max-nodes", type=int, default=1_000_000)
    parser.add_argument("--out", type=Path, default=Path("solver-profile.json"))
    args = parser.parse_args()
    if not 2 <= args.starts <= 12:
        raise SystemExit("--starts must be between 2 and 12")
    if not 2 <= args.options <= 32:
        raise SystemExit("--options must be between 2 and 32")

    hypotheses = _hypotheses(args.starts, args.options)
    cartesian_upper_bound = args.options ** args.starts

    started = perf_counter()
    production = select_global_hypotheses(
        hypotheses,
        max_combinations=args.max_combinations,
    )
    production_ms = (perf_counter() - started) * 1000.0

    started = perf_counter()
    branch_bound = select_global_hypotheses_branch_bound(
        hypotheses,
        max_nodes=args.max_nodes,
    )
    branch_bound_ms = (perf_counter() - started) * 1000.0

    same_selection = tuple(item.fragments for item in production.hypotheses) == tuple(
        item.fragments for item in branch_bound.hypotheses
    )
    report = {
        "schema_version": 1,
        "fixture": {
            "kind": "deterministic-synthetic-hypothesis-profile",
            "starts": args.starts,
            "options_per_start": args.options,
            "cartesian_upper_bound": cartesian_upper_bound,
        },
        "production_selector": {
            "elapsed_ms": round(production_ms, 3),
            "combinations_examined": production.combinations_examined,
            "search_truncated": production.search_truncated,
        },
        "reference_branch_bound": {
            "elapsed_ms": round(branch_bound_ms, 3),
            "nodes_visited": branch_bound.nodes_visited,
            "complete_solutions": branch_bound.complete_solutions,
            "pruned_overlap": branch_bound.pruned_overlap,
            "pruned_bound": branch_bound.pruned_bound,
            "truncated": branch_bound.truncated,
        },
        "selection_equivalent": same_selection,
        "claim_limits": [
            "timing is runner-specific and is not a product performance guarantee",
            "the branch-and-bound selector is a reference path and is not used by production recovery",
            "synthetic hypothesis equivalence does not replace real-recorder validation",
            "a truncated selector result is not an optimum claim",
        ],
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not same_selection:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
