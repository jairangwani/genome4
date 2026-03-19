"""Regression detection — did the agent fix the problem or make it worse?

After an agent works on a task:
- Task fixed? → Progress.
- Task NOT fixed AND new critical errors? → Regression. Revert.
- Task NOT fixed, no new criticals? → No progress, but not a regression.
"""

import os
import yaml

from src.node import Task


def detect_regression(assigned_task: Task, before: list[Task], after: list[Task]) -> str | None:
    """Compare before/after task lists. Returns regression description or None."""
    before_msgs = {t.message for t in before}
    after_msgs = {t.message for t in after}

    assigned_fixed = assigned_task.message not in after_msgs

    if assigned_fixed:
        return None  # Task was fixed — no regression

    # Task NOT fixed. Check if agent also broke things.
    new_critical = [
        t for t in after
        if t.severity == "error" and t.priority <= 2
        and t.message not in before_msgs
    ]

    if new_critical:
        msgs = "; ".join(t.message[:80] for t in new_critical[:3])
        return f"Did not fix assigned task AND created new critical errors: {msgs}"

    return None  # No regression, just no progress


def log_regression(plan_dir: str, task: Task, description: str):
    """Append regression to plan/regression_log.yaml."""
    log_path = os.path.join(plan_dir, "regression_log.yaml")
    entry = {
        "task": task.message[:200],
        "node": task.node_name,
        "regression": description[:300],
    }

    existing = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or []
        except Exception:
            existing = []

    existing.append(entry)

    with open(log_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False)


def load_regression_history(plan_dir: str) -> str:
    """Load recent regression history for agent context."""
    log_path = os.path.join(plan_dir, "regression_log.yaml")
    if not os.path.exists(log_path):
        return ""

    try:
        with open(log_path, encoding="utf-8") as f:
            entries = yaml.safe_load(f) or []
    except Exception:
        return ""

    if not entries:
        return ""

    recent = entries[-5:]
    lines = ["RECENT REGRESSIONS (avoid these patterns):"]
    for e in recent:
        lines.append(f"  - {e.get('task', '')[:100]}: {e.get('regression', '')[:100]}")
    return "\n".join(lines)
