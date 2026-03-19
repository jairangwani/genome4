"""genome4 Engine — the convergence loop.

Load nodes → validate → route → fix → repeat.
The engine is a compiler. It reads Python. It runs checks. It routes problems.
It has no opinions about quality, phases, or node types.

Supports parallel agent dispatch with serial apply.
"""

import os
import subprocess
import yaml
import shutil

from src.loader import load_genome
from src.validator import validate_genome, prioritize
from src.regression import detect_regression, log_regression, load_regression_history
from src.node import Task


def _get_current_phase(tasks: list, phase_order: list[str]) -> str | None:
    """Find the first phase with unresolved error tasks."""
    for phase in phase_order:
        if [t for t in tasks if t.phase == phase and t.severity == "error"]:
            return phase
    for phase in phase_order:
        if [t for t in tasks if t.phase == phase and t.severity == "warning"]:
            return phase
    return None


def check(project_dir: str) -> tuple:
    """Validate genome and write status + issues."""
    genome = load_genome(project_dir)
    issues = validate_genome(genome)
    _write_status(genome, issues)
    _write_issues(genome.plan_dir, issues)
    return genome, issues


def converge(project_dir: str, agent_manager):
    """Main convergence loop. Runs until 0 issues or stuck."""

    _bootstrap_hr_agent(project_dir)
    _git_commit(project_dir, "genome4: bootstrap")

    genome, issues = check(project_dir)
    config = _load_config(genome)
    max_parallel = config.get("max_parallel", 1)
    phase_order = config.get("phases", ["structural", "planning", "review", "dev", "test"])

    print(f"  Config: convergence={config['convergence']}, max_parallel={max_parallel}")

    stuck_count = 0
    last_error_count = float("inf")
    revert_counts: dict[str, int] = {}
    last_feedback = ""
    pending: dict[str, dict] = {}

    while True:
        # Phase check: only when no agents are pending (drain guard)
        if not pending:
            genome, issues = check(project_dir)

            # Run runnable nodes (tests/pipelines)
            current_phase = _get_current_phase(issues, phase_order)
            ran_any = False
            if current_phase in ("dev", "test", None):
                for node in genome.all_nodes():
                    if not getattr(node, "runnable", False):
                        continue
                    print(f"  Running: {node.name}")
                    ran_any = True
                    try:
                        result = node.run(project_dir)
                        status = "PASS" if result.get("success") else "FAIL"
                        print(f"  {node.name}: {status}")
                    except Exception as e:
                        print(f"  {node.name}: ERROR ({e})")

            if ran_any:
                issues = validate_genome(genome)

            errors = [i for i in issues if i.severity == "error"]
            warnings = [i for i in issues if i.severity == "warning"]
            current_phase = _get_current_phase(issues, phase_order)

            if current_phase:
                phase_tasks = [i for i in issues if i.phase == current_phase]
                phase_errors = [i for i in phase_tasks if i.severity == "error"]
                print(f"\n-- Phase: {current_phase} | {len(phase_errors)} errors, "
                      f"{len(phase_tasks)-len(phase_errors)} warnings | "
                      f"Total: {len(issues)} tasks --")
            else:
                print(f"\n-- All phases complete | {len(issues)} remaining --")

            # Converged?
            if config["convergence"] == "strict":
                if not errors and not warnings:
                    print("\nOK: Converged (strict).")
                    agent_manager.kill()
                    return
            else:
                if not errors:
                    print("\nOK: Converged.")
                    agent_manager.kill()
                    return

        # Dispatch: pick tasks for idle agents
        if not pending:
            phase_eligible = [i for i in issues if i.phase == current_phase] if current_phase else issues
            eligible = [i for i in phase_eligible
                        if revert_counts.get(i.message, 0) < config["max_reverts"]]
            if not eligible:
                eligible = [i for i in issues
                            if revert_counts.get(i.message, 0) < config["max_reverts"]]
            if not eligible:
                print(f"\nFAIL: All tasks skipped. {len(issues)} remain.")
                agent_manager.kill()
                return

            _git_commit(project_dir, "genome4: pre-agent snapshot")

            dispatched: set[str] = set()
            for task in eligible:
                owner = _find_owner(task, genome)
                if not owner or owner.name in dispatched:
                    continue

                context_nodes = owner.before_work({"node_name": task.node_name}, genome) if hasattr(owner, "before_work") else []
                context_files = [n._source_file for n in context_nodes if n and n._source_file]
                regression_history = load_regression_history(genome.plan_dir)

                print(f"  Dispatching to {owner.name}: {task.message[:80]}...")
                handle = agent_manager.assign_task_async({
                    "issue": task,
                    "context_files": context_files,
                    "regression_history": regression_history,
                    "feedback": last_feedback,
                    "agent_node": owner,
                })

                if handle and not handle.get("error"):
                    pending[owner.name] = {
                        "handle": handle, "task": task,
                        "before_issues": list(issues),
                        "owner": owner, "before_genome": genome,
                    }
                    dispatched.add(owner.name)
                else:
                    err = handle.get("error", "unknown") if handle else "no handle"
                    print(f"  Failed to dispatch to {owner.name}: {err}")

                if len(dispatched) >= max_parallel:
                    break

            if not pending:
                stuck_count += 1
                if stuck_count >= config["stuck_threshold"]:
                    print(f"\nFAIL: Stuck.")
                    agent_manager.kill()
                    return
                continue

            if len(pending) > 1:
                print(f"  {len(pending)} agents working in parallel...")

        # Collect: wait for any agent to finish
        finished_name, dispatch_id = agent_manager.wait_for_any_completion(
            timeout=config.get("agent_timeout", 300))

        if finished_name is None:
            print(f"  TIMEOUT: No agent responded.")
            for name in list(pending.keys()):
                agent_manager.kill(name)
            pending.clear()
            stuck_count += 1
            if stuck_count >= config["stuck_threshold"]:
                print(f"\nFAIL: Stuck — agents timing out.")
                agent_manager.kill()
                return
            continue

        if finished_name not in pending:
            continue

        # Check dispatch ID to filter stale signals from killed agents
        expected_id = pending[finished_name].get("handle", {}).get("dispatch_id", "")
        if dispatch_id and expected_id and dispatch_id != expected_id:
            continue  # stale signal from old reader thread

        info = pending.pop(finished_name)
        result = agent_manager.collect_result(info["handle"], timeout=10)

        print(f"  {finished_name} finished. Applying...")

        if not result.get("success"):
            print(f"  Agent failed: {result.get('error', 'unknown')}")
            stuck_count += 1
            if stuck_count >= config["stuck_threshold"] and not pending:
                print(f"\nFAIL: Stuck.")
                agent_manager.kill()
                return
            continue

        # Apply: serial commit + validate + regression check
        top = info["task"]
        owner = info["owner"]
        before_issues = info["before_issues"]

        after_genome, after_issues = check(project_dir)
        after_errors = [i for i in after_issues if i.severity == "error"]

        # After-work checks
        if hasattr(owner, "after_work"):
            for v in owner.after_work({"node_name": top.node_name}, after_genome, info.get("before_genome")):
                print(f"  After-work: {v.message}")

        # Task obsolescence
        task_still_exists = top.message in {i.message for i in after_issues}
        if not task_still_exists and not pending:
            _git_commit(project_dir, f"genome4: {finished_name} (task resolved)")
            print(f"  Task already resolved. Committed.")
            stuck_count = 0
            continue

        # Regression check
        regression = detect_regression(top, before_issues, after_issues)
        if regression:
            print(f"  REGRESSION: {regression}")
            log_regression(after_genome.plan_dir, top, regression)
            revert_counts[top.message] = revert_counts.get(top.message, 0) + 1
            if revert_counts[top.message] >= config["max_reverts"]:
                print(f"  Skipping — reverted {config['max_reverts']} times.")
            if not pending:
                try:
                    subprocess.run(["git", "reset", "--hard", "HEAD~1"],
                                   cwd=project_dir, capture_output=True, timeout=30)
                    subprocess.run(["git", "clean", "-fd"],
                                   cwd=project_dir, capture_output=True, timeout=30)
                    print(f"  Reverted.")
                except Exception:
                    print(f"  WARNING: Could not revert.")
            else:
                _git_commit(project_dir, f"genome4: {finished_name} (regression, pending agents)")
            continue

        _git_commit(project_dir, f"genome4: {finished_name}")

        # Feedback
        before_msgs = {i.message for i in before_issues}
        after_msgs = {i.message for i in after_issues}
        resolved = [i for i in before_issues if i.message not in after_msgs]
        new_issues = [i for i in after_issues if i.message not in before_msgs]
        parts = []
        if resolved:
            parts.append(f"RESOLVED: {'; '.join(i.message[:60] for i in resolved[:3])}")
        if new_issues:
            parts.append(f"NEW: {'; '.join(i.message[:60] for i in new_issues[:3])}")
        last_feedback = "\n".join(parts) if parts else ""

        # Progress tracking
        assigned_fixed = top.message not in after_msgs
        if assigned_fixed:
            print(f"  FIXED: {top.message[:80]}")
            stuck_count = 0
        else:
            print(f"  NOT FIXED: {top.message[:80]}")
            stuck_count += 1

        print(f"  Tasks: {len(before_issues)} -> {len(after_issues)} ({len(after_errors)} errors)")

        if len(after_errors) < last_error_count:
            last_error_count = len(after_errors)
            stuck_count = 0

        if stuck_count >= config["stuck_threshold"] and not pending:
            print(f"\nFAIL: Stuck — no progress for {config['stuck_threshold']} passes.")
            agent_manager.kill()
            return


# -- Bootstrap --

def _bootstrap_hr_agent(project_dir: str):
    """Create HR Agent if no agents exist."""
    plan_dir = os.path.join(project_dir, "plan")
    os.makedirs(plan_dir, exist_ok=True)

    # Check if any agent files exist
    for root, dirs, files in os.walk(plan_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".py") and not f.startswith("_"):
                try:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        if "AgentNode" in fh.read() or "type = \"agent\"" in open(os.path.join(root, f), encoding="utf-8").read():
                            return
                except Exception:
                    pass

    print("  No agents found. Bootstrapping HR Agent...")

    hr_code = '''"""HR Agent — creates and manages the agent team."""
from genome4 import Node, Task


class HRAgent(Node):
    name = "HR Agent"
    type = "agent"
    description = (
        "Manages agent lifecycle. Creates specialist agents, assigns node ownership. "
        "Reads project context and creates the right team for the job."
    )

    model = "claude-sonnet-4-6"
    capabilities = ["team-management", "domain-analysis", "agent-creation"]
    edges = {}

    knowledge = [
        "Bootstrapped by genome4 engine. Create specialist agents and assign ownership.",
        "Read plan/context.yaml for project description.",
        "You can create any node type. Write validate() to check your team's work.",
    ]

    def validate(self, genome):
        tasks = []
        agents = genome.nodes_by_type("agent")
        if len(agents) == 1 and agents[0].name == self.name:
            tasks.append(Task(
                f"{self.name}: must create specialist agents for this project",
                self.name, phase="structural", priority=3,
                check="hr-must-create-team",
                suggestion="Read context.yaml, create specialists, assign ownership",
            ))
        return tasks
'''

    hr_path = os.path.join(plan_dir, "hr_agent.py")
    with open(hr_path, "w", encoding="utf-8") as f:
        f.write(hr_code)

    # Copy seed nodes if available
    _seed_project(plan_dir, project_dir)
    print(f"  Created HR Agent.")


def _seed_project(plan_dir: str, project_dir: str):
    """Copy seed nodes from context.yaml seed selection."""
    context_path = os.path.join(plan_dir, "context.yaml")
    seed_name = "blank"

    if os.path.exists(context_path):
        try:
            with open(context_path, encoding="utf-8") as f:
                ctx = yaml.safe_load(f) or {}
            seed_name = ctx.get("seed", ctx.get("template", "blank"))
        except Exception:
            pass

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    seed_dir = os.path.join(engine_dir, "..", "seeds", seed_name)

    if not os.path.exists(seed_dir):
        seed_dir = os.path.join(engine_dir, "..", "seeds", "blank")

    if not os.path.exists(seed_dir):
        return

    for filename in os.listdir(seed_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            src = os.path.join(seed_dir, filename)
            dst = os.path.join(plan_dir, filename)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    print(f"  Seeded from: {seed_name}")


# -- Helpers --

def _find_owner(task: Task, genome) -> 'Node | None':
    if task.node_name:
        node = genome.get(task.node_name)
        if node:
            owner = node.get_owner(genome)
            if owner:
                return owner
    agents = genome.nodes_by_type("agent")
    return agents[0] if agents else None


def _load_config(genome) -> dict:
    defaults = {
        "convergence": "strict",
        "stuck_threshold": 5,
        "max_reverts": 3,
        "agent_timeout": 300,
        "max_parallel": 1,
        "phases": ["structural", "planning", "review", "dev", "test"],
    }
    for node in genome.nodes_by_type("config"):
        for key in defaults:
            if hasattr(node, key):
                defaults[key] = getattr(node, key)
    return defaults


def _git_commit(project_dir: str, message: str):
    try:
        subprocess.run(["git", "add", "-A"], cwd=project_dir, capture_output=True, timeout=30)
        subprocess.run(["git", "commit", "-m", message, "--allow-empty"],
                       cwd=project_dir, capture_output=True, timeout=30)
    except Exception:
        pass


def _write_status(genome, tasks):
    errors = [t for t in tasks if t.severity == "error"]
    warnings = [t for t in tasks if t.severity == "warning"]
    status = {
        "generator": "genome4",
        "counts": {"nodes": len(genome.nodes), "journeys": len(genome.journeys)},
        "issues": {"total": len(tasks), "errors": len(errors), "warnings": len(warnings)},
        "converged": not errors and not warnings,
    }
    with open(os.path.join(genome.plan_dir, "status.yaml"), "w", encoding="utf-8") as f:
        yaml.dump(status, f, default_flow_style=False)


def _write_issues(plan_dir, tasks):
    data = [{"priority": f"P{t.priority}", "phase": t.phase, "severity": t.severity,
             "node": t.node_name or None, "message": t.message} for t in tasks]
    with open(os.path.join(plan_dir, "issues.yaml"), "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)
