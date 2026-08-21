from __future__ import annotations

from vidrensic.recovery.graph import ContinuationEdge, FragmentNode, ReconstructionGraph
from vidrensic.recovery.solver import solve_node_disjoint_paths


def _node(graph: ReconstructionGraph, node_id: str, index: int) -> None:
    graph.add_node(FragmentNode(node_id=node_id, physical_index=index, offset=index * 4096, size=4096))


def test_global_solver_resolves_crossing_competition_better_than_local_greedy() -> None:
    graph = ReconstructionGraph()
    for node_id, index in (
        ("A0", 0),
        ("B0", 1),
        ("X", 2),
        ("Y", 3),
        ("B1", 4),
        ("A1", 5),
    ):
        _node(graph, node_id, index)

    # A locally greedy A0 decision would take X (cost 1) and force B0 to Y
    # (cost 10). The globally better assignment is A0->Y and B0->X.
    for source, target, cost in (
        ("A0", "X", 1.0),
        ("A0", "Y", 2.0),
        ("B0", "X", 1.1),
        ("B0", "Y", 10.0),
        ("X", "B1", 1.0),
        ("Y", "A1", 1.0),
    ):
        graph.add_edge(ContinuationEdge(source, target, cost, {"synthetic": 1.0}))

    result = solve_node_disjoint_paths(
        graph,
        ["A0", "B0"],
        continuation_reward=20.0,
    )
    paths = {path.start_id: path.node_ids for path in result.paths}
    assert paths["A0"] == ("A0", "Y", "A1")
    assert paths["B0"] == ("B0", "X", "B1")
    flattened = [node for path in result.paths for node in path.node_ids]
    assert len(flattened) == len(set(flattened))
    assert result.global_alternative_margin is not None
    assert result.global_alternative_margin > 0


def test_global_solver_stops_instead_of_accepting_weak_continuation() -> None:
    graph = ReconstructionGraph()
    _node(graph, "S", 0)
    _node(graph, "weak", 1)
    graph.add_edge(ContinuationEdge("S", "weak", 100.0, {"structural": 1.0}))

    result = solve_node_disjoint_paths(
        graph,
        ["S"],
        continuation_reward=50.0,
    )
    assert result.paths[0].node_ids == ("S",)
    assert result.selected_edges == ()
    assert result.total_benefit == 0
