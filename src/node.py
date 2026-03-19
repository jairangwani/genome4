"""Node — the universal building block.

Everything in genome4 is a node. A node is a Python file with:
- name, type, description (identity)
- edges (connections to other nodes)
- validate() (self-checking — returns tasks when something is wrong)
- doc/decisions/knowledge (structured memory)

Agents create whatever node types they need. There are no required types.
The engine doesn't care what type a node is — it just loads Python and calls validate().
"""


class Task:
    """A message from a node to its owner: 'this needs fixing.'

    The engine routes tasks to the owning agent via owned_by edges.
    """

    def __init__(self, message: str, node_name: str = "",
                 phase: str = "planning", priority: int = 5,
                 severity: str = "error", check: str = "",
                 suggestion: str = ""):
        self.message = message
        self.node_name = node_name
        self.phase = phase
        self.priority = priority
        self.severity = severity
        self.check = check
        self.suggestion = suggestion

    def __repr__(self):
        return f"Task(P{self.priority}/{self.severity}: {self.message[:60]})"


# Backward compat alias
Issue = Task


class Node:
    """Base class for all genome4 nodes.

    Agents extend this with whatever fields and validate() logic they need.
    The engine only requires: name (non-empty), validate() returns list[Task].
    """

    name: str = ""
    type: str = ""
    description: str = ""

    properties: dict = {}
    edges: dict = {}
    files: list[str] = []

    # Structured knowledge
    doc: str = ""                       # PERMANENT: what this node IS
    decisions: list[str] = []           # PERMANENT: why choices were made
    knowledge: list[str] = []           # PRUNABLE: work history (last 8)

    # Engine-managed (set by loader)
    _source_file: str = ""
    _mtime: float = 0

    def __init__(self):
        # Ensure mutable defaults are per-instance, not shared across class
        if type(self).properties is Node.properties:
            self.properties = {}
        else:
            self.properties = dict(type(self).properties)

        if type(self).edges is Node.edges:
            self.edges = {}
        else:
            self.edges = dict(type(self).edges)

        if type(self).files is Node.files:
            self.files = []
        else:
            self.files = list(type(self).files)

        if type(self).decisions is Node.decisions:
            self.decisions = []
        else:
            self.decisions = list(type(self).decisions)

        if type(self).knowledge is Node.knowledge:
            self.knowledge = []
        else:
            self.knowledge = list(type(self).knowledge)

    def validate(self, genome) -> list[Task]:
        """Check this node. Return tasks for anything wrong.

        Override in subclasses to add project-specific checks.
        The engine calls this on every node, every cycle.
        """
        tasks = []

        if not self.name:
            tasks.append(Task("Node has no name", phase="structural", priority=1))

        if not self.description:
            tasks.append(Task(
                f"'{self.name}': no description",
                self.name, phase="structural", priority=3, severity="warning",
                check="no-description",
            ))

        # Type consistency: if a parent class defines type, subclass must match
        for cls in type(self).__mro__:
            if cls is Node or cls is type(self):
                continue
            parent_type = cls.__dict__.get("type")
            if parent_type and self.type != parent_type:
                tasks.append(Task(
                    f"'{self.name}' extends {cls.__name__} but has type='{self.type}' "
                    f"(expected '{parent_type}')",
                    self.name, phase="structural", priority=1,
                    check="type-mismatch",
                ))
                break

        return tasks

    def get_owner(self, genome) -> 'Node | None':
        """Get the agent that owns this node."""
        owner_name = self.edges.get("owned_by")
        if owner_name:
            return genome.get(owner_name)
        return None

    def get_owned_nodes(self, genome) -> list['Node']:
        """Get all nodes owned by this node (agent)."""
        return [n for n in genome.all_nodes()
                if n.edges.get("owned_by") == self.name]

    def get_connections(self, genome) -> list['Node']:
        """Get all nodes connected via edges (in any direction)."""
        connected = []
        # Outgoing
        for etype, targets in self.edges.items():
            if etype.startswith("_"):
                continue
            target_list = targets if isinstance(targets, list) else [targets]
            for t in target_list:
                target_name = t[0] if isinstance(t, tuple) else t
                node = genome.get(target_name)
                if node:
                    connected.append(node)
        # Incoming
        for node in genome.all_nodes():
            for etype, targets in node.edges.items():
                if etype.startswith("_"):
                    continue
                target_list = targets if isinstance(targets, list) else [targets]
                for t in target_list:
                    target_name = t[0] if isinstance(t, tuple) else t
                    if target_name == self.name and node not in connected:
                        connected.append(node)
        return connected

    def has_recent_review(self) -> bool:
        """Check if this node has been recently reviewed."""
        if not self.knowledge:
            return False
        recent = " ".join(str(k) for k in self.knowledge[-3:]).lower()
        return any(term in recent for term in
                   ["reviewed", "approved", "challenged", "verified"])

    def __repr__(self):
        return f"<{type(self).__name__} '{self.name}'>"
