"""Seed base classes — optional types agents can import.

Usage: from genome4.seeds import ServiceNode, PersonaNode, etc.
These are NOT required. Agents can write 'class MyNode(Node)' directly.
These just provide common validate() patterns so agents don't reinvent wheels.
"""

import os
import re
import subprocess
from genome4 import Node, Task


class ServiceNode(Node):
    """A running system component (API, worker, service)."""
    type = "service"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not (self.properties.get("failure_modes") or getattr(self, "failure_modes", None)):
            tasks.append(Task(
                f"{self.name}: service should have failure_modes",
                self.name, phase="planning", priority=5,
                check="service-no-failure-modes",
            ))

        for f in (self.files or []):
            if not os.path.exists(os.path.join(genome.project_dir, f)):
                tasks.append(Task(
                    f"{self.name}: file '{f}' does not exist",
                    self.name, phase="dev", priority=7,
                    check="files-must-exist",
                ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"{self.name}: no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class PersonaNode(Node):
    """A human user or threat actor."""
    type = "persona"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not (self.properties.get("goals") or getattr(self, "goals", None)):
            tasks.append(Task(
                f"{self.name}: persona should have goals",
                self.name, phase="planning", priority=5,
                check="persona-no-goals",
            ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"{self.name}: no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class JourneyNode(Node):
    """A step-by-step flow. Steps reference nodes in [brackets]."""
    type = "journey"
    steps: list = []

    def __init__(self):
        super().__init__()
        if type(self).steps is JourneyNode.steps:
            self.steps = []
        else:
            self.steps = list(type(self).steps)

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not self.steps:
            tasks.append(Task(
                f"{self.name}: journey has no steps",
                self.name, phase="planning", priority=5,
                check="journey-no-steps",
            ))

        return tasks

    @staticmethod
    def extract_node_name(step):
        match = re.search(r'\[(.+?)\]', step)
        return match.group(1) if match else None


class AgentNode(Node):
    """An AI agent that works on tasks."""
    type = "agent"
    model: str = "claude-sonnet-4-6"
    capabilities: list = []

    def __init__(self):
        super().__init__()
        if type(self).capabilities is AgentNode.capabilities:
            self.capabilities = []
        else:
            self.capabilities = list(type(self).capabilities)

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        owned = self.get_owned_nodes(genome)
        if not owned:
            tasks.append(Task(
                f"{self.name}: agent owns 0 nodes",
                self.name, phase="structural", priority=3, severity="warning",
                check="agent-no-nodes",
            ))

        return tasks

    def before_work(self, task, genome) -> list:
        """Gather context nodes for the agent before working."""
        context = [self]
        if task.get("node_name"):
            target = genome.get(task["node_name"])
            if target:
                context.append(target)
                context.extend(target.get_connections(genome))
        # Include knowledge nodes (guides, quality checks)
        for node in genome.all_nodes():
            if node.knowledge and node.type not in ("service", "persona", "use_case", "store", "agent"):
                context.append(node)
        return context

    def after_work(self, task, genome, before_genome) -> list[Task]:
        """Check workflow compliance after agent finishes."""
        issues = []
        target_name = task.get("node_name")
        if target_name and before_genome:
            target = genome.get(target_name)
            before_target = before_genome.get(target_name)
            if target and before_target:
                if len(target.knowledge or []) <= len(before_target.knowledge or []):
                    issues.append(Task(
                        f"{self.name}: did not add knowledge to {target_name}",
                        self.name, phase="review", priority=7, severity="warning",
                        check="after-work-knowledge",
                    ))
        return issues


class StoreNode(Node):
    """A data layer (database, cache, file store)."""
    type = "store"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not (self.properties.get("schema") or getattr(self, "schema", None)):
            tasks.append(Task(
                f"{self.name}: store should have schema",
                self.name, phase="planning", priority=5,
                check="store-no-schema",
            ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"{self.name}: no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class TestNode(Node):
    """A live test the engine runs. Results can't be faked."""
    type = "test"
    test_target: str = ""
    test_command: str = ""
    test_file: str = ""
    last_result: dict = {}

    @property
    def runnable(self):
        return bool(self.test_command or self.test_file)

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not self.test_command and not self.test_file:
            tasks.append(Task(
                f"{self.name}: test needs test_command or test_file",
                self.name, phase="test", priority=8,
                check="test-no-command",
            ))

        if self.last_result.get("success") is False:
            target = self.test_target or self.name
            error_msg = self.last_result.get("error", "test failed")
            tasks.append(Task(
                f"Test '{self.name}' FAILED: {error_msg[:200]}",
                target, phase="test", priority=8,
                check="test-failed",
            ))

        return tasks

    def run(self, project_dir: str) -> dict:
        command = self.test_command
        if not command and self.test_file:
            ext = self.test_file.rsplit(".", 1)[-1] if "." in self.test_file else ""
            runners = {
                "spec.ts": "npx playwright test", "spec.js": "npx playwright test",
                "test.ts": "npx jest", "test.js": "npx jest",
                "py": "python -m pytest",
            }
            for suffix, runner in runners.items():
                if self.test_file.endswith(suffix):
                    command = f"{runner} {self.test_file}"
                    break
            if not command:
                command = f"node {self.test_file}"

        if not command:
            return {"success": False, "error": "No test command"}

        try:
            result = subprocess.run(
                command, shell=True, cwd=project_dir,
                capture_output=True, text=True, timeout=120)
            self.last_result = {
                "success": result.returncode == 0,
                "output": result.stdout[-1000:] if result.stdout else "",
                "error": result.stderr[-500:] if result.stderr else "",
            }
            return self.last_result
        except subprocess.TimeoutExpired:
            self.last_result = {"success": False, "error": "Test timed out (120s)"}
            return self.last_result
        except Exception as e:
            self.last_result = {"success": False, "error": str(e)[:500]}
            return self.last_result


class ConfigNode(Node):
    """Engine configuration."""
    type = "config"
    convergence: str = "strict"
    max_parallel: int = 1
    stuck_threshold: int = 5
    max_reverts: int = 3
    agent_timeout: int = 300
    phases: list = ["structural", "planning", "review", "dev", "test"]

    def validate(self, genome) -> list[Task]:
        return []
