"""genome4 CLI — check, converge, init."""

import sys
import os

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import check, converge
from src.node import Task


def main():
    args = sys.argv[1:]
    command = args[0] if args else None
    path = args[1] if len(args) > 1 else "."
    project_dir = os.path.abspath(path)

    if command == "check":
        print(f"Checking genome at {project_dir}/plan/\n")
        genome, issues = check(project_dir)
        for t in issues:
            icon = "x" if t.severity == "error" else "!" if t.severity == "warning" else "-"
            node = f" [{t.node_name}]" if t.node_name else ""
            print(f"  {icon} [{t.phase}]{node} {t.message}")
        errors = [i for i in issues if i.severity == "error"]
        print(f"\n{len(genome.nodes)} nodes, {len(genome.journeys)} journeys")
        print(f"{len(issues)} issues ({len(errors)} errors)")
        if errors:
            sys.exit(1)

    elif command == "converge":
        print(f"Converging genome at {project_dir}/plan/")
        print("Runs until converged or stuck. Ctrl+C to stop.\n")

        from src.agent_manager import create_agent_manager
        agent_mgr = create_agent_manager(project_dir)

        try:
            converge(project_dir, agent_mgr)
        except KeyboardInterrupt:
            print("\nStopping...")
            agent_mgr.kill()
        except Exception as e:
            import traceback
            crash_log = os.path.join(project_dir, "plan", "engine-crash.log")
            tb = traceback.format_exc()
            print(f"\nENGINE CRASH: {e}\n{tb}")
            with open(crash_log, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"\n--- {datetime.datetime.now()} ---\n{tb}\n")
            agent_mgr.kill()
            sys.exit(1)

    elif command == "status":
        status_path = os.path.join(project_dir, "plan", "status.yaml")
        if os.path.exists(status_path):
            with open(status_path, encoding="utf-8") as f:
                print(f.read())
        else:
            print("No status.yaml. Run `genome4 check` first.")

    elif command == "init":
        seed = "blank"
        for a in args[1:]:
            if a.startswith("--seed="):
                seed = a.split("=", 1)[1]
            elif not a.startswith("-"):
                project_dir = os.path.abspath(a)

        print(f"Initializing genome4 project at {project_dir}")
        plan_dir = os.path.join(project_dir, "plan")
        os.makedirs(plan_dir, exist_ok=True)

        # Create context.yaml if it doesn't exist
        ctx_path = os.path.join(plan_dir, "context.yaml")
        if not os.path.exists(ctx_path):
            import yaml
            yaml.dump({"seed": seed, "description": "New genome4 project"},
                      open(ctx_path, "w", encoding="utf-8"), default_flow_style=False)
            print(f"  Created context.yaml (seed={seed})")

        print(f"  Run 'genome4 converge {project_dir}' to start.")

    else:
        print("""
genome4 — The Agent Protocol

Commands:
  genome4 check [path]                  Validate, print tasks
  genome4 converge [path]               Run convergence loop with agents
  genome4 status [path]                 Show status.yaml
  genome4 init [path] --seed=<name>     Initialize project (blank, simple-software, complex-software)
""")


if __name__ == "__main__":
    main()
