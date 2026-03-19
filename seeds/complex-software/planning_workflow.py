"""Planning Workflow — guides agents through persona-first planning.

This is a seed node. Agents can modify this workflow for their project.
The validate() fires holistic planning tasks and depth checks.
"""
import os
import yaml
from genome4 import Node, Task


class PlanningWorkflow(Node):
    name = "Planning Workflow"
    type = "workflow"
    description = "Persona-first planning workflow with holistic planning and review."
    edges = {}

    knowledge = [
        """PLANNING STEPS (agents follow in order):

1. PERSONAS — Human users and threat actors ONLY.
   Primary users, secondary users, threat actors.
   Each extends PersonaNode (or Node with type="persona").

2. USE CASES — For every persona: happy path, error path, edge cases, abuse.
   Connect to personas via edges.

3. JOURNEYS — Step-by-step flows for every significant use case.
   Steps: "1. [NodeName] does something"
   Personas INITIATE. Services PROCESS. Stores PERSIST.

4. ARCHITECTURE — ServiceNode and StoreNode for every system component.
   Each service needs failure_modes. Each store needs schema.

5. CODE — Source files for services. Only after planning + review complete.

6. TESTS — TestNode for each service. Engine runs them independently.
""",
    ]

    def validate(self, genome) -> list[Task]:
        tasks = []

        context = self._read_context(genome)
        if not context:
            return tasks

        reference = context.get("planning", {}).get("reference", "")
        personas = genome.nodes_by_type("persona")
        services = genome.nodes_by_type("service")
        use_cases = genome.nodes_by_type("use_case")
        stores = genome.nodes_by_type("store")

        # --- HOLISTIC PLANNING ---
        # Has any agent marked initial planning as complete?
        initial_plan_done = any(
            "initial plan complete" in (
                " ".join(a.knowledge or []) + " " + (getattr(a, 'doc', '') or '')
            ).lower()
            for a in genome.nodes_by_type("agent")
        )

        if not initial_plan_done and reference:
            summary = (
                f"CURRENT STATE: {len(personas)} personas, "
                f"{len(use_cases)} use cases, {len(genome.journeys)} journeys, "
                f"{len(services)} services, {len(stores)} stores."
            )
            tasks.append(Task(
                f"Plan the project. Read {reference} for the full spec. {summary} "
                f"Create ALL personas, use cases, journeys, and architecture. "
                f"Only add 'initial plan complete' to your doc field when "
                f"EVERYTHING in the spec is covered.",
                self.name, phase="planning", priority=1,
                check="needs-initial-plan",
            ))
            return tasks

        # --- DEPTH CHECKS (after initial plan) ---

        # Personas need use cases
        for p in personas:
            if not [uc for uc in use_cases if p.name in str(uc.edges)]:
                tasks.append(Task(
                    f"Persona '{p.name}' has no use cases.",
                    p.name, phase="planning", priority=5,
                    check="persona-no-usecases",
                ))

        # Use cases need journeys
        for uc in use_cases:
            if not genome.node_in_any_journey(uc.name):
                tasks.append(Task(
                    f"Use case '{uc.name}' has no journey.",
                    uc.name, phase="planning", priority=5,
                    check="usecase-no-journey",
                ))

        # Services need failure modes (only if using ServiceNode seed)
        for svc in services:
            if not (svc.properties.get("failure_modes") or getattr(svc, "failure_modes", None)):
                tasks.append(Task(
                    f"Service '{svc.name}': no failure_modes.",
                    svc.name, phase="planning", priority=5,
                    check="service-no-failure-modes",
                ))

        # --- HOLISTIC REVIEW ---
        review_done = any(
            "review complete" in (
                " ".join(a.knowledge or []) + " " + (getattr(a, 'doc', '') or '')
            ).lower()
            for a in genome.nodes_by_type("agent")
        )

        # Review invalidation: if plan nodes changed after review
        if review_done:
            review_agent_mtime = 0
            for a in genome.nodes_by_type("agent"):
                agent_text = (" ".join(a.knowledge or []) + " " + (getattr(a, 'doc', '') or '')).lower()
                if "review complete" in agent_text:
                    review_agent_mtime = max(review_agent_mtime, getattr(a, '_mtime', 0))

            plan_types = {"persona", "use_case", "journey", "service", "store"}
            for node in list(genome.all_nodes()) + list(genome.journeys.values()):
                if node.type in plan_types and getattr(node, '_mtime', 0) > review_agent_mtime:
                    review_done = False
                    break

        if not review_done and reference:
            summary = (
                f"PLAN STATE: {len(personas)} personas, "
                f"{len(use_cases)} use cases, {len(genome.journeys)} journeys, "
                f"{len(services)} services, {len(stores)} stores."
            )
            tasks.append(Task(
                f"Review the ENTIRE plan against the spec. Read {reference}. "
                f"{summary} Challenge everything. Are all user types covered? "
                f"Are use cases comprehensive? Are journeys deep with failure "
                f"points? Is architecture production-ready? "
                f"Add 'review complete' to your doc field when genuinely satisfied.",
                self.name, phase="review", priority=6, severity="warning",
                check="needs-holistic-review",
            ))

        return tasks

    def _read_context(self, genome) -> dict:
        ctx_path = os.path.join(genome.project_dir, "plan", "context.yaml")
        if not os.path.exists(ctx_path):
            return {}
        try:
            with open(ctx_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
