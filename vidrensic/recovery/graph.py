from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FragmentNode:
    node_id: str
    physical_index: int
    offset: int
    size: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContinuationEdge:
    source_id: str
    target_id: str
    score: float
    evidence: dict[str, float] = field(default_factory=dict)
    hard_valid: bool = True


class ReconstructionGraph:
    """Small deterministic graph container used by format plugins.

    The global multi-camera solver is intentionally a separate future component;
    this class captures evidence without forcing a local heuristic to become the
    long-term public data model.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, FragmentNode] = {}
        self.edges: dict[str, list[ContinuationEdge]] = {}

    def add_node(self, node: FragmentNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate node: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, edge: ContinuationEdge) -> None:
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise KeyError("both edge endpoints must exist")
        if edge.source_id == edge.target_id:
            raise ValueError("self-loop is invalid for fragment continuation")
        self.edges.setdefault(edge.source_id, []).append(edge)

    def candidates(self, source_id: str) -> tuple[ContinuationEdge, ...]:
        return tuple(
            sorted(
                (edge for edge in self.edges.get(source_id, []) if edge.hard_valid),
                key=lambda edge: (edge.score, edge.target_id),
            )
        )

    def validate_no_duplicate_physical_indices(self) -> None:
        indices = [node.physical_index for node in self.nodes.values()]
        if len(indices) != len(set(indices)):
            raise ValueError("graph contains duplicate physical fragment indices")
