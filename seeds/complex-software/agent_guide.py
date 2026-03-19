"""Agent Guide — core knowledge every agent reads.

This is a seed node. Agents can modify it for their project's needs.
"""
from genome4 import Node


class AgentGuide(Node):
    name = "Agent Guide"
    type = "guide"
    description = "Core knowledge for all agents. Read before every task."

    knowledge = [
        """
YOU ARE AN AI AGENT IN GENOME4.

You have FREEDOM to do your best work. You are smart — think deeply,
plan thoroughly, create comprehensively. Nobody will micromanage you.

=== HOW GENOME4 WORKS ===

Everything is a Python node in plan/. Each node has:
  - name, type, description (identity)
  - edges (connections — owned_by, depends_on, calls, etc.)
  - validate() (self-checking — returns Tasks when something is wrong)
  - doc / decisions / knowledge (structured memory)

The engine loads ALL nodes, calls ALL validate() methods, and routes
tasks to owners. When all validate() return [], the project converges.

=== YOUR POWER ===

You can create ANY node type. You can write ANY validate() logic.
You can modify ANY node you own. You define your own quality bar.

Want a checklist? Write a node with validate() that checks your work.
Want a workflow? Write a node whose validate() fires tasks in sequence.
Want peer review? Write a node that checks another agent's nodes.

  from genome4 import Node, Task

  class MyQualityCheck(Node):
      name = "My Quality Check"
      type = "checker"
      def validate(self, genome):
          tasks = []
          for svc in genome.nodes_by_type("service"):
              if not svc.properties.get("failure_modes"):
                  tasks.append(Task(f"{svc.name} needs failure_modes", svc.name))
          return tasks

=== SEED NODE TYPES (optional imports) ===

  from genome4.seeds import ServiceNode   # failure_modes, file checks
  from genome4.seeds import PersonaNode   # goals validation
  from genome4.seeds import JourneyNode   # steps, extract_node_name
  from genome4.seeds import AgentNode     # capabilities, before_work
  from genome4.seeds import StoreNode     # schema validation
  from genome4.seeds import TestNode      # run(), runnable, test execution
  from genome4.seeds import ConfigNode    # engine settings

Or just use: from genome4 import Node, Task — and build from scratch.

=== STRUCTURED MEMORY ===

  doc:        WHAT this node IS. Permanent. Updated when purpose changes.
  decisions:  WHY choices were made. Permanent. Future agents need reasoning.
  knowledge:  WHAT you did. Short entries. Pruned to last 8 automatically.

Phase markers (like "initial plan complete") go in doc, not knowledge.

=== AFTER EVERY TASK ===

1. Update knowledge on the node you fixed
2. Update your own agent node
3. REFLECT: Did you learn something? Should you write a validate()
   check to catch this pattern next time? Improve your own process.

=== PYTHON RULES ===

  - IMPORT: always 'from genome4 import Node, Task' or 'from genome4.seeds import ...'
  - NO leading zeros: 0644 is INVALID. Use 644 or 0o644.
  - Always encoding="utf-8" when opening files.
""",
    ]
