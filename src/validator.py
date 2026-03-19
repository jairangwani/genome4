"""Validator — universal graph checks only.

The validator calls validate() on every node and adds universal graph checks:
1. Load errors (broken Python files)
2. Dangling edges (references to non-existent nodes)
3. Cascade staleness (upstream changed, downstream needs review)

Everything else is node-level. If a project needs depth checks, quality gates,
or persona validation — agents write nodes that check for those things.
The engine has no opinions.
"""

import os
from src.genome import Genome
from src.node import Task


def validate_genome(genome: Genome) -> list[Task]:
    """Run universal validation. Returns sorted tasks."""
    tasks = []

    # 1. Load errors — broken files become P1 structural tasks
    for filepath, error in genome.load_errors:
        rel_path = os.path.relpath(filepath, genome.project_dir)
        tasks.append(Task(
            f"File '{rel_path}' failed to load: {error[:200]}",
            node_name=rel_path, phase="structural", priority=1,
            check="load-error",
            suggestion=f"Fix the syntax error in {rel_path}",
        ))

    # 2. Each node validates itself
    for node in genome.all_nodes():
        tasks.extend(node.validate(genome))

    # Also validate journeys
    for journey in genome.journeys.values():
        tasks.extend(journey.validate(genome))

    # 3. Dangling edges — universal graph integrity
    tasks.extend(_check_dangling_edges(genome))

    # 4. Cascade staleness — universal dependency tracking
    tasks.extend(_check_cascade_staleness(genome))

    return prioritize(tasks)


def prioritize(tasks: list[Task]) -> list[Task]:
    """Sort by phase, then priority, then severity."""
    phase_order = {
        "structural": 0, "planning": 1, "review": 2,
        "dev": 3, "test": 4,
    }
    severity_order = {"error": 0, "warning": 1, "info": 2}
    return sorted(tasks, key=lambda t: (
        phase_order.get(t.phase, 99),
        t.priority,
        severity_order.get(t.severity, 3),
    ))


def _check_dangling_edges(genome: Genome) -> list[Task]:
    """Edges must reference nodes that exist."""
    tasks = []
    all_names = set(genome.nodes.keys()) | set(genome.journeys.keys())

    for node in list(genome.nodes.values()) + list(genome.journeys.values()):
        for etype, targets in node.edges.items():
            if etype.startswith("_"):
                continue
            target_list = targets if isinstance(targets, list) else [targets]
            for t in target_list:
                target_name = t[0] if isinstance(t, tuple) else t
                if target_name and target_name not in all_names:
                    tasks.append(Task(
                        f"Edge from '{node.name}' references non-existent '{target_name}'",
                        node_name=node.name, phase="structural", priority=2,
                        check="dangling-edge",
                        suggestion=f"Create '{target_name}' or remove the edge",
                    ))
    return tasks


def _check_cascade_staleness(genome: Genome) -> list[Task]:
    """When an upstream node changes, downstreams may be stale."""
    tasks = []
    stale: dict[str, str] = {}

    # Direct staleness: if a node I depend on (point to) changed after me, I'm stale
    for node in genome.all_nodes():
        # Check both directions — depends_on targets and nodes pointing to me
        deps = set()
        for n in genome.downstreams(node):  # nodes I point to (my dependencies)
            deps.add(n.name)
        for n in genome.upstreams(node):    # nodes that point to me
            deps.add(n.name)

        for dep_name in deps:
            dep = genome.get(dep_name)
            if dep and dep._mtime > node._mtime > 0:
                stale[node.name] = f"'{dep.name}' was modified after '{node.name}'"

    # Propagate recursively (BFS)
    propagated = set()
    queue = list(stale.keys())
    while queue:
        current = queue.pop(0)
        if current in propagated:
            continue
        propagated.add(current)
        current_node = genome.get(current)
        if not current_node:
            continue
        for downstream in genome.downstreams(current_node):
            if downstream.name not in stale:
                stale[downstream.name] = f"cascade from '{current}'"
                queue.append(downstream.name)

    # Create tasks (skip config/guide types, skip recently reviewed)
    skip_types = {"config", "guide"}
    for name, reason in stale.items():
        node = genome.get(name)
        if not node or node.type in skip_types:
            continue
        if node.has_recent_review():
            continue
        tasks.append(Task(
            f"'{name}' may be stale: {reason}",
            name, phase="planning", priority=3, severity="warning",
            check="cascade-staleness",
            suggestion=f"Review '{name}' — an upstream dependency changed",
        ))

    return tasks
