from __future__ import annotations

from vidrensic.plugins.wfs.branch_bound import select_global_hypotheses_branch_bound
from vidrensic.plugins.wfs.global_reconstruct import WFSPathHypothesis, select_global_hypotheses


def _h(start: int, fragments: tuple[int, ...], cost: float, *, unresolved: int = 0):
    return WFSPathHypothesis(
        start_fragment=start,
        fragments=fragments,
        total_cost=cost,
        ambiguous_steps=1 if len(fragments) > 1 else 0,
        unresolved_steps=unresolved,
        candidate_counts=(2,) if len(fragments) > 1 else (),
        terminal_reason="synthetic",
    )


def test_branch_bound_matches_production_selector_on_competing_paths() -> None:
    options = {
        10: (
            _h(10, (10, 30, 40), 2.0),
            _h(10, (10, 31, 41), 3.0),
            _h(10, (10, 32), 0.5),
        ),
        20: (
            _h(20, (20, 30, 50, 60), 2.0),
            _h(20, (20, 33, 51), 1.0),
        ),
        25: (
            _h(25, (25, 40, 70), 1.0),
            _h(25, (25, 42, 72), 2.0),
        ),
    }
    reference = select_global_hypotheses(options, max_combinations=100_000)
    branch_bound = select_global_hypotheses_branch_bound(options)

    assert branch_bound.truncated is False
    assert tuple(item.fragments for item in branch_bound.hypotheses) == tuple(
        item.fragments for item in reference.hypotheses
    )


def test_branch_bound_records_overlap_and_bound_pruning() -> None:
    options = {
        1: tuple(_h(1, (1, 100 + i), float(i)) for i in range(8)),
        2: tuple(_h(2, (2, 100 + i), float(i)) for i in range(8)),
        3: tuple(_h(3, (3, 200 + i), float(i)) for i in range(8)),
    }
    result = select_global_hypotheses_branch_bound(options)
    assert result.truncated is False
    assert result.complete_solutions > 0
    assert result.pruned_overlap > 0
    assert result.pruned_bound > 0


def test_branch_bound_node_limit_is_explicitly_truncated_after_first_solution() -> None:
    options = {
        1: tuple(_h(1, (1, 10 + i), float(i)) for i in range(5)),
        2: tuple(_h(2, (2, 20 + i), float(i)) for i in range(5)),
    }
    result = select_global_hypotheses_branch_bound(options, max_nodes=4)
    assert result.truncated is True
    assert result.complete_solutions >= 1
