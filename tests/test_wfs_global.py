from __future__ import annotations

from vidrensic.plugins.wfs.global_reconstruct import (
    WFSPathHypothesis,
    select_global_hypotheses,
)


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


def test_global_selection_resolves_cross_start_fragment_competition() -> None:
    # A greedy choice for start 10 would consume fragment 30. Globally, start
    # 20 needs fragment 30 to retain a longer valid path, while start 10 can
    # take 31 and preserve all continuations.
    options = {
        10: (
            _h(10, (10, 30, 40), 2.0),
            _h(10, (10, 31, 41), 3.0),
        ),
        20: (
            _h(20, (20, 30, 50, 60), 2.0),
            _h(20, (20, 32), 1.0),
        ),
    }

    result = select_global_hypotheses(options)
    selected = {item.start_fragment: item.fragments for item in result.hypotheses}
    assert selected[10] == (10, 31, 41)
    assert selected[20] == (20, 30, 50, 60)
    assert result.total_continuations == 5
    assert set(selected[10]).isdisjoint(selected[20])
    assert result.search_truncated is False


def test_global_selection_prefers_fewer_unresolved_paths_before_distance_cost() -> None:
    options = {
        1: (
            _h(1, (1, 3), 1.0, unresolved=1),
            _h(1, (1, 4), 9.0, unresolved=0),
        ),
        2: (_h(2, (2, 5), 1.0),),
    }
    result = select_global_hypotheses(options)
    selected = {item.start_fragment: item.fragments for item in result.hypotheses}
    assert selected[1] == (1, 4)
    assert result.total_unresolved_steps == 0


def test_global_selection_retains_second_best_margin_as_ambiguity_evidence() -> None:
    options = {
        1: (_h(1, (1, 3), 1.0), _h(1, (1, 4), 1.5)),
        2: (_h(2, (2, 5), 1.0),),
    }
    result = select_global_hypotheses(options)
    assert result.second_best_continuations == result.total_continuations
    assert result.alternative_cost_margin == 0.5
    assert result.has_close_alternative is True


def test_global_selection_marks_bounded_search_truncation() -> None:
    options = {
        1: tuple(_h(1, (1, value), float(value)) for value in range(10, 15)),
        2: tuple(_h(2, (2, value), float(value)) for value in range(20, 25)),
    }
    result = select_global_hypotheses(options, max_combinations=3)
    assert result.combinations_examined == 3
    assert result.search_truncated is True


def test_global_selection_rejects_start_mismatch() -> None:
    bad = {1: (_h(2, (2,), 0.0),)}
    try:
        select_global_hypotheses(bad)
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("expected mismatched hypothesis start to be rejected")
