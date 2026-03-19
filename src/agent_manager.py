"""Agent Manager — spawns persistent Claude Code processes.

Each agent node maps to a persistent process. Communication via NDJSON stdin/stdout.
Supports parallel dispatch: multiple agents think simultaneously, results applied serially.
"""

import json
import subprocess
import os
import threading
import queue
import uuid


class AgentManager:
    def __init__(self, project_dir: str, task_timeout: int = 300):
        self.project_dir = project_dir
        self.task_timeout = task_timeout
        self.agents: dict[str, dict] = {}
        self.completion_queue: queue.Queue = queue.Queue()

    def assign_task(self, task: dict) -> dict:
        """Assign a task synchronously. Blocks until done."""
        handle = self.assign_task_async(task)
        if not handle or handle.get("error"):
            return {"success": False, "error": handle.get("error", "no handle") if handle else "no handle"}
        return self.collect_result(handle)

    def assign_task_async(self, task: dict) -> dict | None:
        """Dispatch task to agent, return immediately with a handle."""
        agent_node = task.get("agent_node")
        if not agent_node:
            return {"error": "No agent node provided"}

        name = agent_node.name
        process = self._get_or_spawn(agent_node)
        if not process:
            return {"error": f"Failed to spawn agent '{name}'"}

        prompt = self._build_prompt(task)
        return self._send_message_async(name, prompt)

    def collect_result(self, handle: dict, timeout: float = None) -> dict:
        """Block until an async task completes."""
        if handle.get("error"):
            return {"success": False, "error": handle["error"]}

        name = handle["agent_name"]
        result_queue = handle["result_queue"]
        info = self.agents.get(name)
        actual_timeout = timeout or self.task_timeout

        try:
            item = result_queue.get(timeout=actual_timeout)
            if item["type"] == "result":
                return {"success": True, "text": self._extract_text(item["msg"])}
            else:
                if info:
                    info["alive"] = False
                return {"success": False, "error": item["error"]}
        except queue.Empty:
            print(f"  TIMEOUT: Agent '{name}' did not respond within {actual_timeout}s")
            if info:
                try:
                    info["process"].kill()
                except Exception:
                    pass
                info["alive"] = False
            return {"success": False, "error": f"Agent '{name}' timed out after {actual_timeout}s"}

    def wait_for_any_completion(self, timeout: float = None) -> tuple[str, str] | tuple[None, None]:
        """Block until any dispatched agent finishes. Returns (agent_name, dispatch_id)."""
        try:
            item = self.completion_queue.get(timeout=timeout or self.task_timeout)
            if isinstance(item, tuple):
                return item  # (name, dispatch_id)
            return item, ""  # legacy compat
        except queue.Empty:
            return None, None

    def kill(self, name: str = None):
        """Kill agent process(es)."""
        targets = [name] if name else list(self.agents.keys())
        for n in targets:
            info = self.agents.get(n)
            if info and info.get("process"):
                try:
                    proc = info["process"]
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                       capture_output=True, timeout=10)
                    else:
                        proc.kill()
                except Exception:
                    pass
            if n in self.agents:
                del self.agents[n]

    def _get_or_spawn(self, agent_node) -> dict | None:
        """Get existing or spawn new agent process."""
        name = agent_node.name
        info = self.agents.get(name)
        if info and info.get("alive"):
            return info

        model = getattr(agent_node, "model", "claude-sonnet-4-6")
        desc = getattr(agent_node, "description", "")

        env = {**os.environ}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        system_prompt = (
            f'You are "{name}". {desc} '
            f'Read ALL files listed in each task — they contain genome4 instructions and context.'
        )

        args = [
            "claude",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--model", model,
            "--dangerously-skip-permissions",
            "--verbose",
            "--system-prompt", system_prompt,
        ]

        try:
            proc = subprocess.Popen(
                args, cwd=self.project_dir, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            info = {"process": proc, "name": name, "alive": True}
            self.agents[name] = info
            return info
        except Exception as e:
            print(f"  Failed to spawn {name}: {e}")
            return None

    def _send_message_async(self, name: str, message: str) -> dict:
        """Send NDJSON message and return handle immediately."""
        info = self.agents.get(name)
        if not info or not info.get("alive"):
            return {"error": f"Agent '{name}' not alive"}

        proc = info["process"]
        ndjson = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": message},
        })

        try:
            proc.stdin.write((ndjson + "\n").encode())
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            info["alive"] = False
            return {"error": f"Agent '{name}' stdin broken — process crashed"}

        result_q = queue.Queue()
        completion_q = self.completion_queue
        dispatch_id = str(uuid.uuid4())[:8]

        def _reader():
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        result_q.put({"type": "error", "error": "stdout closed"})
                        completion_q.put((name, dispatch_id))
                        return
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "result":
                            result_q.put({"type": "result", "msg": msg})
                            completion_q.put((name, dispatch_id))
                            return
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                result_q.put({"type": "error", "error": str(e)})
                completion_q.put((name, dispatch_id))

        threading.Thread(target=_reader, daemon=True).start()
        return {"agent_name": name, "result_queue": result_q, "dispatch_id": dispatch_id}

    def _extract_text(self, msg: dict) -> str:
        if isinstance(msg.get("result"), str):
            return msg["result"]
        if isinstance(msg.get("text"), str):
            return msg["text"]
        if isinstance(msg.get("content"), list):
            return "\n".join(c.get("text", "") for c in msg["content"] if c.get("text"))
        return json.dumps(msg)

    def _build_prompt(self, task: dict) -> str:
        """Build the task prompt for the agent."""
        issue = task["issue"]
        lines = [
            "GENOME4 BASICS:",
            "- Everything is a Python node in plan/. You ARE a node.",
            "- IMPORT: use 'from genome4 import Node, Task'",
            "  For seed types: 'from genome4.seeds import ServiceNode' (optional)",
            "- Every node must have: name, type, description.",
            "- Add owned_by to edges dict so tasks route to you.",
            "- You can create, modify, or delete ANY node you own.",
            "- You can write your own validate() to check your own work.",
            "- After fixing, update your knowledge. Reflect: should you improve your process?",
            "",
            "TASK: Fix issue on " + (f'node "{issue.node_name}"' if issue.node_name else "the project"),
            f"ISSUE: {issue.message}",
            f"PRIORITY: P{issue.priority} ({issue.severity})",
        ]

        if issue.suggestion:
            lines.append(f"SUGGESTION: {issue.suggestion}")

        # Include reference doc
        context_files = list(task.get("context_files", []))
        context_yaml_path = os.path.join(self.project_dir, "plan", "context.yaml")
        if os.path.exists(context_yaml_path):
            try:
                import yaml
                with open(context_yaml_path, encoding="utf-8") as cf:
                    ctx = yaml.safe_load(cf) or {}
                ref = ctx.get("planning", {}).get("reference", "")
                if ref:
                    ref_path = os.path.join(self.project_dir, ref)
                    if os.path.exists(ref_path) and ref_path not in context_files:
                        context_files.insert(0, ref_path)
            except Exception:
                pass

        lines.append("\nFILES TO READ (read ALL before making changes):")
        for f in context_files:
            rel = os.path.relpath(f, self.project_dir)
            lines.append(f"  {rel}")

        if task.get("feedback"):
            lines.append(f"\nFEEDBACK FROM LAST TASK:\n{task['feedback']}")

        if task.get("regression_history"):
            lines.append(f"\n{task['regression_history']}")

        lines.append("\nAFTER FIXING:")
        lines.append("1. Add a knowledge entry to the node you fixed")
        lines.append("2. Update your own agent node knowledge")
        lines.append("3. REFLECT: Did you learn something? Should you update your own validate() to catch this next time?")

        # HR Agent instructions
        agent_node = task.get("agent_node")
        if agent_node and "team-management" in getattr(agent_node, "capabilities", []):
            lines.append(self._hr_instructions())

        return "\n".join(lines)

    def _hr_instructions(self) -> str:
        return """
HR AGENT INSTRUCTIONS:
- Create specialist agents for this project's needs.
- Assign every domain node an owner via owned_by edge.
- Name agents descriptively: "Backend Agent", "Security Agent". Never "Agent 1".
- Each new agent needs at least one domain node to own.
- You can create quality-check nodes that validate the team's work.
"""


def create_agent_manager(project_dir: str) -> AgentManager:
    return AgentManager(project_dir)
