from __future__ import annotations

import pytest

import vidrensic.plugins.wfs.global_reconstruct as global_wfs
from vidrensic.plugins.wfs.global_reconstruct import (
    WFSPathHypothesis,
    enumerate_path_hypotheses,
    select_global_hypotheses,
)
from vidrensic.plugins.wfs.reconstruct import WFSChain


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
    with pytest.raises(ValueError, match="mismatch"):
        select_global_hypotheses(bad)


def test_path_enumerator_preserves_branch_specific_carry_state(monkeypatch) -> None:
    monkeypatch.setattr(
        global_wfs,
        "init_chain",
        lambda *args, **kwargs: WFSChain(1, 1, [1], b"seed", True),
    )

    observed_tails: list[tuple[int, bytes | None]] = []

    def fake_candidates(fd, state, used, stop_fragment, **kwargs):
        observed_tails.append((state.current_fragment, state.tail))
        if state.current_fragment == 1:
            return [(1.0, 3, b"carry-a"), (2.0, 4, b"carry-b")]
        if state.current_fragment == 3:
            assert state.tail == b"carry-a"
            return [(1.0, 5, None)]
        if state.current_fragment == 4:
            assert state.tail == b"carry-b"
            return []
        return []

    monkeypatch.setattr(global_wfs, "candidate_list", fake_candidates)
    result = enumerate_path_hypotheses(
        99,
        1,
        10,
        near=2,
        far=8,
        beam_width=8,
        max_depth=8,
    )
    paths = {item.fragments: item for item in result}
    assert (1, 3, 5) in paths
    assert paths[(1, 3, 5)].terminal_reason == "terminal-padding"
    assert (1, 4) in paths
    assert paths[(1, 4)].unresolved_steps == 1
    assert (3, b"carry-a") in observed_tails
    assert (4, b"carry-b") in observed_tails


def test_path_enumerator_reports_invalid_or_terminal_start(monkeypatch) -> None:
    monkeypatch.setattr(
        global_wfs,
        "init_chain",
        lambda *args, **kwargs: WFSChain(2, 2, [2], None, False, unresolved_steps=0),
    )
    result = enumerate_path_hypotheses(1, 2, 3)
    assert result[0].fragments == (2,)
    assert result[0].terminal_reason == "terminal-padding"


def test_path_enumerator_marks_max_depth(monkeypatch) -> None:
    monkeypatch.setattr(
        global_wfs,
        "init_chain",
        lambda *args, **kwargs: WFSChain(1, 1, [1], b"seed", True),
    )

    def endless(fd, state, used, stop_fragment, **kwargs):
        return [(1.0, state.current_fragment + 1, b"next")]

    monkeypatch.setattr(global_wfs, "candidate_list", endless)
    result = enumerate_path_hypotheses(1, 1, 20, max_depth=1)
    assert result[0].terminal_reason == "max-depth"
    assert result[0].unresolved_steps == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_fragment": -1, "stop_fragment": 2},
        {"start_fragment": 1, "stop_fragment": 1},
        {"start_fragment": 1, "stop_fragment": 2, "near": 0},
        {"start_fragment": 1, "stop_fragment": 2, "candidate_top": 17},
        {"start_fragment": 1, "stop_fragment": 2, "beam_width": 0},
        {"start_fragment": 1, "stop_fragment": 2, "max_hypotheses": 0},
    ],
)
def test_path_enumerator_rejects_invalid_bounds(kwargs) -> None:
    with pytest.raises(ValueError):
        enumerate_path_hypotheses(1, **kwargs)
