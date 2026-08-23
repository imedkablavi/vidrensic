from __future__ import annotations

from dataclasses import dataclass

from vidrensic.plugins.wfs.global_reconstruct import WFSPathHypothesis


@dataclass(frozen=True)
class BranchBoundSelection:
    hypotheses: tuple[WFSPathHypothesis, ...]
    objective_key: tuple
    nodes_visited: int
    complete_solutions: int
    pruned_overlap: int
    pruned_bound: int
    truncated: bool
    notes: tuple[str, ...]


def _hypothesis_key(item: WFSPathHypothesis) -> tuple:
    return (
        -item.continuations,
        item.unresolved_steps,
        item.ambiguous_steps,
        item.total_cost,
        item.fragments,
    )


def _solution_key(items: tuple[WFSPathHypothesis, ...]) -> tuple:
    return (
        -sum(item.continuations for item in items),
        sum(item.unresolved_steps for item in items),
        sum(item.ambiguous_steps for item in items),
        sum(item.total_cost for item in items),
        tuple(item.fragments for item in items),
    )


def select_global_hypotheses_branch_bound(
    hypotheses_by_start: dict[int, tuple[WFSPathHypothesis, ...]],
    *,
    max_nodes: int = 1_000_000,
) -> BranchBoundSelection:
    """Reference B&B selector for profiling/equivalence work.

    This function is intentionally separate from the production WFS selector.
    It may be promoted only after equivalence, performance and real-fixture
    validation. A truncated result is never an optimum claim.
    """

    if not hypotheses_by_start:
        raise ValueError("at least one start hypothesis set is required")
    if max_nodes <= 0:
        raise ValueError("max_nodes must be positive")

    starts = tuple(sorted(hypotheses_by_start))
    for start in starts:
        options = hypotheses_by_start[start]
        if not options:
            raise ValueError(f"start {start} has no hypotheses")
        if any(item.start_fragment != start for item in options):
            raise ValueError(f"hypothesis start mismatch for {start}")

    ordered = {
        start: tuple(sorted(hypotheses_by_start[start], key=_hypothesis_key)) for start in starts
    }
    exploration = tuple(sorted(starts, key=lambda start: (len(ordered[start]), start)))

    # Independent optimistic components are safe lower bounds for the
    # lexicographic objective. Equality is not pruned because fragment tuples
    # can still decide a deterministic tie.
    suffix_max_cont: list[int] = [0] * (len(exploration) + 1)
    suffix_min_unresolved: list[int] = [0] * (len(exploration) + 1)
    suffix_min_ambiguous: list[int] = [0] * (len(exploration) + 1)
    suffix_min_cost: list[float] = [0.0] * (len(exploration) + 1)
    for position in range(len(exploration) - 1, -1, -1):
        start = exploration[position]
        options = ordered[start]
        suffix_max_cont[position] = suffix_max_cont[position + 1] + max(
            item.continuations for item in options
        )
        suffix_min_unresolved[position] = suffix_min_unresolved[position + 1] + min(
            item.unresolved_steps for item in options
        )
        suffix_min_ambiguous[position] = suffix_min_ambiguous[position + 1] + min(
            item.ambiguous_steps for item in options
        )
        suffix_min_cost[position] = suffix_min_cost[position + 1] + min(
            item.total_cost for item in options
        )

    selected: dict[int, WFSPathHypothesis] = {}
    best: tuple[WFSPathHypothesis, ...] | None = None
    best_key: tuple | None = None
    nodes_visited = 0
    complete_solutions = 0
    pruned_overlap = 0
    pruned_bound = 0
    truncated = False

    def walk(
        position: int,
        used: frozenset[int],
        continuations: int,
        unresolved: int,
        ambiguous: int,
        cost: float,
    ) -> None:
        nonlocal best, best_key, nodes_visited, complete_solutions
        nonlocal pruned_overlap, pruned_bound, truncated
        if truncated:
            return
        nodes_visited += 1
        if nodes_visited > max_nodes:
            truncated = True
            return

        if best_key is not None:
            optimistic = (
                -(continuations + suffix_max_cont[position]),
                unresolved + suffix_min_unresolved[position],
                ambiguous + suffix_min_ambiguous[position],
                cost + suffix_min_cost[position],
            )
            if optimistic > best_key[:4]:
                pruned_bound += 1
                return

        if position == len(exploration):
            complete_solutions += 1
            items = tuple(selected[start] for start in starts)
            key = _solution_key(items)
            if best_key is None or key < best_key:
                best = items
                best_key = key
            return

        start = exploration[position]
        for option in ordered[start]:
            if option.fragment_set & used:
                pruned_overlap += 1
                continue
            selected[start] = option
            walk(
                position + 1,
                used | option.fragment_set,
                continuations + option.continuations,
                unresolved + option.unresolved_steps,
                ambiguous + option.ambiguous_steps,
                cost + option.total_cost,
            )
            selected.pop(start, None)
            if truncated:
                return

    walk(0, frozenset(), 0, 0, 0, 0.0)
    if best is None or best_key is None:
        if truncated:
            raise RuntimeError("branch-and-bound node limit reached before a complete solution")
        raise RuntimeError("no globally disjoint WFS path combination exists")

    return BranchBoundSelection(
        hypotheses=best,
        objective_key=best_key,
        nodes_visited=nodes_visited,
        complete_solutions=complete_solutions,
        pruned_overlap=pruned_overlap,
        pruned_bound=pruned_bound,
        truncated=truncated,
        notes=(
            "reference branch-and-bound path is not the production selector",
            "optimistic lexicographic bounds prune only branches that cannot beat the current best",
            "truncated=true means the selected result is not an optimum claim",
            "promotion requires equivalence tests, performance data and real-recorder validation",
        ),
    )
