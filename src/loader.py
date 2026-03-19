"""Loader — imports Python node files and builds the Genome.

Reads all .py files from plan/. Each file defines a Node subclass.
Load errors (syntax, import) are tracked — they become structural tasks.
Knowledge is pruned to last 8 entries. Doc and decisions are permanent.
"""

import os
import sys
import types
from pathlib import Path

from src.genome import Genome
from src.node import Node


def load_genome(project_dir: str) -> Genome:
    """Load all Python nodes from plan/ and build the Genome."""
    genome = Genome(project_dir)
    plan_dir = os.path.join(project_dir, "plan")

    if not os.path.exists(plan_dir):
        raise FileNotFoundError(f"No plan/ directory at {project_dir}")

    # Make genome4 base classes available for import
    _ensure_genome4_importable()

    # Walk plan/ recursively — agents can organize however they want
    for root, dirs, files in os.walk(plan_dir):
        # Skip hidden dirs and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

        for filename in files:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(root, filename)
            node, error = _load_node_from_file(filepath)
            if node:
                node._source_file = filepath
                node._mtime = os.path.getmtime(filepath)

                # Prune knowledge to last 8 (doc and decisions are permanent)
                if node.knowledge and len(node.knowledge) > 8:
                    node.knowledge = node.knowledge[-8:]

                # Journeys go to separate dict for graph operations
                if node.type == "journey":
                    genome.add_journey(node)
                else:
                    genome.add(node)
            elif error:
                genome.load_errors.append((filepath, error))

    genome.build_graph()
    return genome


def _load_node_from_file(filepath: str) -> tuple[Node | None, str | None]:
    """Import a Python file and extract the Node subclass instance."""
    mtime = int(os.path.getmtime(filepath) * 1000)
    module_name = f"_genome4_node_{Path(filepath).stem}_{mtime}"

    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        code = compile(source, filepath, "exec")
        module = types.ModuleType(module_name)
        module.__file__ = filepath
        module.__name__ = module_name
        sys.modules[module_name] = module
        exec(code, module.__dict__)

        node_class = _find_node_class(module)
        if node_class:
            instance = node_class()
            if instance.name:
                return instance, None

        return None, None
    except Exception as e:
        print(f"  Warning: Failed to load {filepath}: {e}")
        return None, str(e)


def _find_node_class(module) -> type | None:
    """Find the first Node subclass defined in a module."""
    for name in dir(module):
        obj = getattr(module, name)
        if (isinstance(obj, type)
                and issubclass(obj, Node)
                and obj is not Node
                and obj.__module__ == module.__name__):
            return obj
    return None


_genome4_installed = False

def _ensure_genome4_importable():
    """Make 'genome4' importable so nodes can do 'from genome4 import Node'."""
    global _genome4_installed
    if _genome4_installed:
        return

    from src import node as node_module

    genome4_mod = types.ModuleType("genome4")
    for attr_name in ["Node", "Task", "Issue"]:
        setattr(genome4_mod, attr_name, getattr(node_module, attr_name))
    sys.modules["genome4"] = genome4_mod

    # Also make seed classes available: from genome4.seeds import ServiceNode
    _install_seeds()

    _genome4_installed = True


def _install_seeds():
    """Make seed base classes importable via 'from genome4.seeds import ServiceNode'."""
    seeds_mod = types.ModuleType("genome4.seeds")
    sys.modules["genome4.seeds"] = seeds_mod

    # Import seed classes if they exist
    seeds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds")
    seed_classes_file = os.path.join(seeds_dir, "base_classes.py")

    if os.path.exists(seed_classes_file):
        try:
            with open(seed_classes_file, "r", encoding="utf-8") as f:
                source = f.read()
            code = compile(source, seed_classes_file, "exec")
            exec(code, seeds_mod.__dict__)
        except Exception as e:
            print(f"  Warning: Failed to load seed classes: {e}")
