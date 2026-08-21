from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Callable

from vidrensic.recovery.graph import ContinuationEdge, ReconstructionGraph


@dataclass(frozen=True)
class SolvedPath:
    start_id: str
    node_ids: tuple[str, ...]
    selected_edges: tuple[ContinuationEdge, ...]
    total_edge_cost: float
    total_benefit: float


@dataclass(frozen=True)
class GlobalSolveResult:
    paths: tuple[SolvedPath, ...]
    selected_edges: tuple[ContinuationEdge, ...]
    total_edge_cost: float
    total_benefit: float
    global_alternative_margin: float | None
    notes: tuple[str, ...]


@dataclass
class _FlowEdge:
    to: int
    rev: int
    capacity: int
    cost: float
    original: ContinuationEdge | None = None


def _add_edge(
    network: list[list[_FlowEdge]],
    source: int,
    target: int,
    capacity: int,
    cost: float,
    *,
    original: ContinuationEdge | None = None,
) -> None:
    forward = _FlowEdge(target, len(network[target]), capacity, cost, original)
    reverse = _FlowEdge(source, len(network[source]), 0, -cost, None)
    network[source].append(forward)
    network[target].append(reverse)


def _shortest_path(network: list[list[_FlowEdge]], source: int, sink: int):
    """Bellman-Ford on residual graph; deterministic tie-breaking by node/edge index."""

    count = len(network)
    distance = [inf] * count
    parent_node = [-1] * count
    parent_edge = [-1] * count
    distance[source] = 0.0

    for _ in range(count - 1):
        changed = False
        for node in range(count):
            if distance[node] == inf:
                continue
            for edge_index, edge in enumerate(network[node]):
                if edge.capacity <= 0:
                    continue
                candidate = distance[node] + edge.cost
                if candidate < distance[edge.to] - 1e-12:
                    distance[edge.to] = candidate
                    parent_node[edge.to] = node
                    parent_edge[edge.to] = edge_index
                    changed = True
                elif abs(candidate - distance[edge.to]) <= 1e-12:
                    old = (parent_node[edge.to], parent_edge[edge.to])
                    new = (node, edge_index)
                    if old == (-1, -1) or new < old:
                        parent_node[edge.to] = node
                        parent_edge[edge.to] = edge_index
                        changed = True
        if not changed:
            break

    if distance[sink] == inf:
        return None
    return distance, parent_node, parent_edge


def _solve_once(
    graph: ReconstructionGraph,
    start_ids: tuple[str, ...],
    *,
    continuation_reward: float,
    max_edge_cost: float | None,
    excluded_edges: frozenset[tuple[str, str]],
    enforce_monotonic: bool,
) -> GlobalSolveResult:
    if not start_ids:
        raise ValueError("at least one start node is required")
    if len(set(start_ids)) != len(start_ids):
        raise ValueError("start node IDs must be unique")
    if continuation_reward <= 0:
        raise ValueError("continuation_reward must be positive")
    for start in start_ids:
        if start not in graph.nodes:
            raise KeyError(f"unknown start node: {start}")
    graph.validate_no_duplicate_physical_indices()

    ordered_ids = tuple(
        sorted(graph.nodes, key=lambda node_id: (graph.nodes[node_id].physical_index, node_id))
    )
    in_index: dict[str, int] = {}
    out_index: dict[str, int] = {}
    # node 0 = super source, node 1 = super sink
    next_index = 2
    for node_id in ordered_ids:
        in_index[node_id] = next_index
        out_index[node_id] = next_index + 1
        next_index += 2
    source = 0
    sink = 1
    network: list[list[_FlowEdge]] = [[] for _ in range(next_index)]

    starts = set(start_ids)
    for node_id in ordered_ids:
        _add_edge(network, in_index[node_id], out_index[node_id], 1, 0.0)
        # Any path may stop after a node at zero incremental cost. Positive
        # continuation benefit therefore has to justify extending the path.
        _add_edge(network, out_index[node_id], sink, 1, 0.0)

    for start_id in start_ids:
        _add_edge(network, source, in_index[start_id], 1, 0.0)

    accepted_edges: list[ContinuationEdge] = []
    for source_id in ordered_ids:
        source_node = graph.nodes[source_id]
        for edge in graph.candidates(source_id):
            if (edge.source_id, edge.target_id) in excluded_edges:
                continue
            if edge.target_id in starts:
                continue
            if max_edge_cost is not None and edge.score > max_edge_cost:
                continue
            target_node = graph.nodes[edge.target_id]
            if enforce_monotonic and target_node.physical_index <= source_node.physical_index:
                continue
            # Existing graph score is a lower-is-better cost. Convert it into a
            # reward relative to a caller-selected acceptance threshold. Edges at
            # or above the threshold do not improve the objective and are omitted.
            benefit = continuation_reward - edge.score
            if benefit <= 0:
                continue
            _add_edge(
                network,
                out_index[edge.source_id],
                in_index[edge.target_id],
                1,
                -benefit,
                original=edge,
            )
            accepted_edges.append(edge)

    sent = 0
    objective_cost = 0.0
    while sent < len(start_ids):
        shortest = _shortest_path(network, source, sink)
        if shortest is None:
            raise RuntimeError("global solver could not route every start to a valid terminal path")
        distance, parent_node, parent_edge = shortest
        node = sink
        while node != source:
            previous = parent_node[node]
            edge_index = parent_edge[node]
            if previous < 0 or edge_index < 0:
                raise RuntimeError("broken residual predecessor chain")
            edge = network[previous][edge_index]
            edge.capacity -= 1
            network[node][edge.rev].capacity += 1
            node = previous
        objective_cost += distance[sink]
        sent += 1

    selected: list[ContinuationEdge] = []
    for node_edges in network:
        for flow_edge in node_edges:
            if flow_edge.original is not None and flow_edge.capacity == 0:
                selected.append(flow_edge.original)
    selected.sort(
        key=lambda edge: (
            graph.nodes[edge.source_id].physical_index,
            edge.source_id,
            edge.target_id,
        )
    )

    outgoing = {edge.source_id: edge for edge in selected}
    selected_by_pair = {(edge.source_id, edge.target_id): edge for edge in selected}
    paths: list[SolvedPath] = []
    used_nodes: set[str] = set()
    for start_id in start_ids:
        node_ids = [start_id]
        edges: list[ContinuationEdge] = []
        current = start_id
        seen: set[str] = {start_id}
        while current in outgoing:
            edge = outgoing[current]
            target = edge.target_id
            if target in seen:
                raise RuntimeError("global solver produced a continuation cycle")
            seen.add(target)
            node_ids.append(target)
            edges.append(selected_by_pair[(edge.source_id, edge.target_id)])
            current = target
        overlap = used_nodes.intersection(node_ids)
        if overlap:
            raise RuntimeError(f"global solver violated node-disjoint invariant: {sorted(overlap)}")
        used_nodes.update(node_ids)
        edge_cost = sum(edge.score for edge in edges)
        benefit = sum(continuation_reward - edge.score for edge in edges)
        paths.append(
            SolvedPath(
                start_id=start_id,
                node_ids=tuple(node_ids),
                selected_edges=tuple(edges),
                total_edge_cost=edge_cost,
                total_benefit=benefit,
            )
        )

    total_edge_cost = sum(path.total_edge_cost for path in paths)
    total_benefit = -objective_cost
    return GlobalSolveResult(
        paths=tuple(paths),
        selected_edges=tuple(selected),
        total_edge_cost=total_edge_cost,
        total_benefit=total_benefit,
        global_alternative_margin=None,
        notes=(
            "solution is globally node-disjoint across all supplied starts",
            "only hard-valid monotonic edges with positive reward are eligible",
            "edge cost scale and continuation_reward are format/profile parameters and must be validated",
        ),
    )


def solve_node_disjoint_paths(
    graph: ReconstructionGraph,
    start_ids: tuple[str, ...] | list[str],
    *,
    continuation_reward: float,
    max_edge_cost: float | None = None,
    enforce_monotonic: bool = True,
    compute_alternative_margin: bool = True,
    max_margin_edges: int = 64,
) -> GlobalSolveResult:
    """Select globally optimal node-disjoint continuation paths.

    The graph's `ContinuationEdge.score` is treated as a lower-is-better cost.
    A continuation contributes `continuation_reward - score` benefit. This keeps
    weak edges from being selected simply to make paths longer and makes the
    acceptance scale an explicit profile parameter rather than a hidden magic
    constant.
    """

    starts = tuple(start_ids)
    best = _solve_once(
        graph,
        starts,
        continuation_reward=continuation_reward,
        max_edge_cost=max_edge_cost,
        excluded_edges=frozenset(),
        enforce_monotonic=enforce_monotonic,
    )

    margin: float | None = None
    if compute_alternative_margin and best.selected_edges:
        if len(best.selected_edges) <= max_margin_edges:
            alternatives: list[float] = []
            for edge in best.selected_edges:
                alternate = _solve_once(
                    graph,
                    starts,
                    continuation_reward=continuation_reward,
                    max_edge_cost=max_edge_cost,
                    excluded_edges=frozenset({(edge.source_id, edge.target_id)}),
                    enforce_monotonic=enforce_monotonic,
                )
                alternatives.append(best.total_benefit - alternate.total_benefit)
            nonnegative = [max(0.0, value) for value in alternatives]
            margin = min(nonnegative) if nonnegative else None

    return GlobalSolveResult(
        paths=best.paths,
        selected_edges=best.selected_edges,
        total_edge_cost=best.total_edge_cost,
        total_benefit=best.total_benefit,
        global_alternative_margin=margin,
        notes=best.notes
        + (
            "alternative margin is the smallest objective loss when one selected continuation is forbidden"
            if margin is not None
            else "alternative margin was not computed or no continuation edge was selected",
        ),
    )
