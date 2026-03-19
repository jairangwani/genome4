"""Genome — the loaded graph of all nodes.

The Genome object is rebuilt from disk on every engine cycle.
It's ephemeral — no persistent state. The truth is always the Python files.
"""

import os
import re


class Genome:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.plan_dir = os.path.join(project_dir, "plan")
        self.nodes: dict[str, 'Node'] = {}
        self.journeys: dict[str, 'Node'] = {}
        self._graph: dict[str, set[str]] = {}
        self._reverse: dict[str, set[str]] = {}
        self.load_errors: list[tuple[str, str]] = []

    def add(self, node):
        self.nodes[node.name] = node

    def add_journey(self, node):
        self.journeys[node.name] = node

    def get(self, name: str):
        return self.nodes.get(name) or self.journeys.get(name)

    def all_nodes(self) -> list:
        return list(self.nodes.values())

    def nodes_by_type(self, node_type: str) -> list:
        return [n for n in self.nodes.values() if n.type == node_type]

    def build_graph(self):
        """Build adjacency lists from edges."""
        self._graph = {}
        self._reverse = {}
        for node in self.all_nodes():
            self._graph.setdefault(node.name, set())
            for etype, targets in node.edges.items():
                if etype.startswith("_") or etype == "owned_by":
                    continue
                target_list = targets if isinstance(targets, list) else [targets]
                for t in target_list:
                    target_name = t[0] if isinstance(t, tuple) else t
                    if target_name:
                        self._graph.setdefault(node.name, set()).add(target_name)
                        self._reverse.setdefault(target_name, set()).add(node.name)

    def downstreams(self, node) -> list:
        """Nodes that depend on this node (this node is upstream)."""
        return [self.get(n) for n in self._graph.get(node.name, set())
                if self.get(n)]

    def upstreams(self, node) -> list:
        """Nodes this node depends on (upstream of this node)."""
        return [self.get(n) for n in self._reverse.get(node.name, set())
                if self.get(n)]

    def all_downstreams(self, node, visited=None) -> list:
        """All transitive downstreams (BFS)."""
        if visited is None:
            visited = set()
        result = []
        for down in self.downstreams(node):
            if down.name not in visited:
                visited.add(down.name)
                result.append(down)
                result.extend(self.all_downstreams(down, visited))
        return result

    def node_in_any_journey(self, name: str) -> bool:
        """Check if a node is covered by any journey (3 detection paths)."""
        # 1. Step references [NodeName]
        for journey in self.journeys.values():
            if hasattr(journey, 'steps') and hasattr(journey, 'extract_node_name'):
                for step in journey.steps:
                    extracted = journey.extract_node_name(step)
                    if extracted == name:
                        return True

        # 2. Journey edges pointing to this node
        for journey in self.journeys.values():
            for etype, targets in journey.edges.items():
                target_list = targets if isinstance(targets, list) else [targets]
                for t in target_list:
                    target_name = t[0] if isinstance(t, tuple) else t
                    if target_name == name:
                        return True

        # 3. Node's own edges pointing to a journey
        node = self.get(name)
        if node:
            for etype in node.edges:
                if etype in ("journey", "has_journey", "traced_by"):
                    return True

        return False
