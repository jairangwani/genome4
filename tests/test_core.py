"""Core genome4 tests — node, loader, validator, regression."""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.node import Node, Task
from src.genome import Genome
from src.validator import validate_genome, prioritize, _check_dangling_edges, _check_cascade_staleness
from src.regression import detect_regression


# -- Node tests --

def test_node_validate_requires_name():
    n = Node()
    tasks = n.validate(Genome("."))
    assert any("no name" in t.message for t in tasks)


def test_node_validate_warns_no_description():
    n = Node()
    n.name = "Test"
    tasks = n.validate(Genome("."))
    assert any("no description" in t.message for t in tasks)


def test_node_validate_clean():
    n = Node()
    n.name = "Test"
    n.description = "A test node"
    tasks = n.validate(Genome("."))
    assert len(tasks) == 0


def test_node_get_owner():
    g = Genome(".")
    agent = Node()
    agent.name = "My Agent"
    agent.type = "agent"
    g.add(agent)

    service = Node()
    service.name = "My Service"
    service.edges = {"owned_by": "My Agent"}
    g.add(service)

    assert service.get_owner(g).name == "My Agent"


def test_node_get_owner_missing():
    g = Genome(".")
    n = Node()
    n.name = "Orphan"
    g.add(n)
    assert n.get_owner(g) is None


def test_node_mutable_defaults():
    """Each node instance should have its own mutable containers."""
    a = Node()
    b = Node()
    a.edges["test"] = "value"
    assert "test" not in b.edges


# -- Task tests --

def test_task_creation():
    t = Task("Something is wrong", "my_node", priority=1)
    assert t.message == "Something is wrong"
    assert t.node_name == "my_node"
    assert t.priority == 1
    assert t.severity == "error"


# -- Genome tests --

def test_genome_add_and_get():
    g = Genome(".")
    n = Node()
    n.name = "Test"
    g.add(n)
    assert g.get("Test") is n
    assert g.get("Nonexistent") is None


def test_genome_nodes_by_type():
    g = Genome(".")
    a = Node(); a.name = "A"; a.type = "service"; g.add(a)
    b = Node(); b.name = "B"; b.type = "persona"; g.add(b)
    c = Node(); c.name = "C"; c.type = "service"; g.add(c)
    assert len(g.nodes_by_type("service")) == 2
    assert len(g.nodes_by_type("persona")) == 1


def test_genome_graph():
    g = Genome(".")
    a = Node(); a.name = "A"; a.edges = {"depends_on": [("B", "needs it")]}; g.add(a)
    b = Node(); b.name = "B"; g.add(b)
    g.build_graph()
    assert b in g.downstreams(a) or a in g.upstreams(b)


# -- Validator tests --

def test_dangling_edge_detected():
    g = Genome(".")
    n = Node(); n.name = "A"; n.edges = {"calls": "NonExistent"}; g.add(n)
    tasks = _check_dangling_edges(g)
    assert len(tasks) >= 1
    assert any("NonExistent" in t.message for t in tasks)


def test_no_dangling_when_target_exists():
    g = Genome(".")
    a = Node(); a.name = "A"; a.edges = {"calls": "B"}; g.add(a)
    b = Node(); b.name = "B"; g.add(b)
    tasks = _check_dangling_edges(g)
    assert len(tasks) == 0


def test_staleness_detected():
    g = Genome(".")
    upstream = Node(); upstream.name = "Upstream"; upstream._mtime = 200
    downstream = Node(); downstream.name = "Down"; downstream._mtime = 100
    downstream.edges = {"depends_on": [("Upstream", "needs it")]}
    downstream.description = "has desc"
    g.add(upstream); g.add(downstream)
    g.build_graph()
    tasks = _check_cascade_staleness(g)
    assert any("stale" in t.message for t in tasks)


def test_prioritize_phase_ordering():
    tasks = [
        Task("dev task", phase="dev", priority=1),
        Task("planning task", phase="planning", priority=1),
        Task("structural task", phase="structural", priority=1),
    ]
    sorted_tasks = prioritize(tasks)
    assert sorted_tasks[0].phase == "structural"
    assert sorted_tasks[1].phase == "planning"
    assert sorted_tasks[2].phase == "dev"


def test_prioritize_priority_within_phase():
    tasks = [
        Task("low", phase="planning", priority=5),
        Task("high", phase="planning", priority=1),
    ]
    sorted_tasks = prioritize(tasks)
    assert sorted_tasks[0].priority == 1


# -- Regression tests --

def test_regression_task_fixed():
    assigned = Task("Fix X", "node_x")
    before = [Task("Fix X", "node_x"), Task("Fix Y", "node_y")]
    after = [Task("Fix Y", "node_y")]  # X is gone
    assert detect_regression(assigned, before, after) is None


def test_regression_not_fixed_no_new_criticals():
    assigned = Task("Fix X", "node_x")
    before = [Task("Fix X", "node_x")]
    after = [Task("Fix X", "node_x")]  # still there
    assert detect_regression(assigned, before, after) is None


def test_regression_not_fixed_with_new_criticals():
    assigned = Task("Fix X", "node_x")
    before = [Task("Fix X", "node_x")]
    after = [Task("Fix X", "node_x"), Task("New P1 error", "node_z", priority=1)]
    result = detect_regression(assigned, before, after)
    assert result is not None
    assert "critical" in result.lower()


# -- Loader tests (basic) --

def test_loader_missing_plan_dir():
    from src.loader import load_genome
    with pytest.raises(FileNotFoundError):
        load_genome("/nonexistent/path")


def test_loader_empty_plan(tmp_path):
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert len(g.nodes) == 0


def test_loader_loads_node(tmp_path):
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    node_file = plan_dir / "my_node.py"
    node_file.write_text('''
from genome4 import Node
class MyNode(Node):
    name = "My Test Node"
    type = "test"
    description = "A test"
''', encoding="utf-8")

    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert g.get("My Test Node") is not None


def test_loader_tracks_load_errors(tmp_path):
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    bad_file = plan_dir / "broken.py"
    bad_file.write_text("this is not valid python {{{}}", encoding="utf-8")

    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert len(g.load_errors) >= 1


def test_loader_prunes_knowledge(tmp_path):
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    node_file = plan_dir / "chatty.py"
    entries = ", ".join(f'"entry {i}"' for i in range(20))
    node_file.write_text(f'''
from genome4 import Node
class Chatty(Node):
    name = "Chatty"
    type = "test"
    description = "Has lots of knowledge"
    knowledge = [{entries}]
''', encoding="utf-8")

    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    node = g.get("Chatty")
    assert node is not None
    assert len(node.knowledge) == 8
