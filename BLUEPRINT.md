# GENOME4 — The Agent Protocol

## What This Is

A protocol for AI agents to build and manage anything — software, books, organizations, legal documents, research — by writing Python files that describe their work, check their own quality, and communicate with each other.

The engine is a compiler. It reads the Python. It runs the checks. It routes problems to owners. That's all it does.

## The Two Problems

1. **Context limits** — An agent can't hold an entire large project in memory. A 1025-line spec with 16 modules exceeds any single agent's context window.

2. **Tunnel vision** — An agent focuses on its immediate task and forgets what it planned to do. Without reminders, it drifts.

**Nodes solve context.** Each node is a Python file that persists state. Agents read the nodes they need. Edges connect the graph. History lives in doc/decisions/knowledge fields.

**validate() solves tunnel vision.** Agents write their own checklists as Python. The engine runs ALL validate() methods every cycle. If an agent planned 10 steps and forgot step 7, the engine fires step 7 as a task. The agent's OWN plan holds it accountable.

## Core Concepts

### Node

A Python file with:

```python
from genome4 import Node, Task

class MyService(Node):
    name = "Auth Service"
    type = "service"
    description = "Handles authentication"

    edges = {
        "owned_by": "Backend Agent",
        "depends_on": [("Database", "stores credentials")],
    }

    doc = "Permanent: what this node IS"
    decisions = ["Why Ed25519 was chosen over RSA"]
    knowledge = ["2026-03-19: Implemented JWT refresh flow"]

    def validate(self, genome) -> list[Task]:
        tasks = []
        if not self.properties.get("failure_modes"):
            tasks.append(Task("Auth Service needs failure_modes", self.name))
        return tasks
```

Agents create whatever node types they need. There are no required types. A software project might use ServiceNode, PersonaNode, JourneyNode. A book project might use ChapterNode, CharacterNode, ArcNode. The engine doesn't care — it just loads Python and calls validate().

### Task

A message routed from a node to its owner:

```python
class Task:
    message: str      # what needs fixing
    node_name: str    # which node has the problem
    phase: str        # when to address it (optional workflow control)
    priority: int     # urgency (1=highest)
    severity: str     # "error", "warning", "info"
    check: str        # identifier for deduplication
    suggestion: str   # hint for the agent
```

### Engine

A loop:

```
while True:
    genome = load_all_python_files("plan/")
    tasks = []
    for node in genome.all_nodes():
        tasks.extend(node.validate(genome))

    if not tasks:
        print("Converged!")
        return

    top_task = prioritize(tasks)[0]
    owner = find_owner(top_task, genome)

    git_snapshot()
    result = assign_to_agent(owner, top_task)

    if regression_detected():
        git_revert()
    else:
        git_commit()
```

The engine does NOT:
- Define quality — agents do (via validate())
- Enforce phases — agents choose their own workflow
- Restrict node types — agents create whatever they need
- Freeze anything — agents modify any node they own

### Seed Nodes

Pre-built node collections for common patterns. NOT frozen. NOT infrastructure. Just starting points that agents copy, modify, or ignore.

```
genome4 init --seed=complex-software    # personas, services, journeys, depth checks
genome4 init --seed=simple-software     # lighter version
genome4 init --seed=book                # chapters, characters, arcs
genome4 init --seed=blank               # just the engine, no starter nodes
```

Seed nodes are regular nodes. Once copied into the project, agents own them and can change anything.

### Ownership

Every node has `edges = {"owned_by": "Agent Name"}`. This is the routing mechanism — when validate() produces a task on a node, the engine sends it to the owning agent.

Ownership is singular (one owner per node). Agents can transfer ownership by changing the edge. HR Agent (bootstrapped by engine) creates the initial team and assigns ownership.

## Project Structure

```
my-project/
├── plan/
│   ├── auth_service.py          # a node
│   ├── user_persona.py          # a node
│   ├── login_journey.py         # a node
│   ├── my_quality_checks.py     # a node (agent-written validator)
│   ├── backend_agent.py         # a node (agent definition)
│   ├── project_config.py        # a node (engine settings)
│   └── context.yaml             # project description + reference doc path
├── src/                         # source code (created by agents during dev)
├── tests/                       # test files (created by agents during test)
└── docs/                        # reference docs (spec, plans)
```

Everything in plan/ is a node. No subdirectories required (agents can create them if they want). No templates/ vs nodes/ split.

## Engine Architecture

### 1. Loader

Reads all .py files from plan/. For each file:
- Compile and exec the Python
- Find the Node subclass
- Create an instance
- Track load errors (syntax errors → structural tasks)
- Prune knowledge to last 8 entries (doc and decisions are permanent)

Returns a Genome object (graph of all nodes).

### 2. Validator

For each node, call node.validate(genome). Collect all tasks. Sort by priority.

Universal checks (engine-level, not node-level):
- **Load errors** — broken Python files become P1 tasks
- **Dangling edges** — edges referencing non-existent nodes
- **Cascade staleness** — upstream changed, downstream needs review

Everything else is node-level. If a project needs persona-as-service detection, an agent writes a node that checks for it. The engine doesn't have opinions.

### 3. Router

Find the owner of the task's node via owned_by edge. Fallback: first agent. If no agents exist, bootstrap HR Agent.

### 4. Agent Manager

Spawns persistent Claude Code processes (one per agent). Communication via NDJSON stdin/stdout.

Features:
- **Persistent sessions** — agents keep context across tasks
- **Timeout** — 300s default, configurable
- **Parallel dispatch** — multiple agents think simultaneously, results applied serially
- **Completion queue** — engine waits for any agent to finish, processes first responder
- **Windows support** — taskkill /T /F for process cleanup

### 5. Regression Guard

Before agent works: git snapshot. After: compare tasks.
- Assigned task fixed? Progress.
- Assigned task NOT fixed AND new critical errors? Regression → revert.
- Assigned task NOT fixed but no new criticals? No progress, but not regression.

Revert: `git reset --hard HEAD~1 && git clean -fd`

### 6. Git Integration

Every project is a git repo. The engine uses git for:
- **Snapshots** — commit before agent works (revert point)
- **History** — track what changed and when
- **Regression revert** — undo bad agent work cleanly

### 7. Config

A ConfigNode (or any node with config fields) controls engine behavior:

```python
class ProjectConfig(Node):
    name = "Project Config"
    type = "config"

    max_parallel = 2        # agents thinking simultaneously
    stuck_threshold = 5     # fails before engine gives up
    max_reverts = 3         # per-task revert limit
    agent_timeout = 300     # seconds per task
    convergence = "strict"  # "strict" = 0 errors AND 0 warnings
```

## Node Base Class

Minimal. Agents extend as needed.

```python
class Node:
    name: str = ""
    type: str = ""
    description: str = ""

    properties: dict = {}
    edges: dict = {}        # owned_by, depends_on, calls, flows_to, etc.
    files: list[str] = []   # source files this node owns

    # Structured knowledge (agents use these)
    doc: str = ""                    # PERMANENT: what this node IS
    decisions: list[str] = []        # PERMANENT: why choices were made
    knowledge: list[str] = []        # PRUNABLE: work history (last 8)

    def validate(self, genome) -> list[Task]:
        """Return tasks for anything wrong with this node."""
        tasks = []
        if not self.name:
            tasks.append(Task("Node has no name", phase="structural"))
        if not self.description:
            tasks.append(Task("Node has no description", phase="structural"))
        return tasks

    def get_owner(self, genome):
        owner_name = self.edges.get("owned_by")
        return genome.get(owner_name) if owner_name else None
```

## Seed Node Library

Optional base classes agents can import:

```python
from genome4 import Node                    # base
from genome4.seeds import ServiceNode       # has failure_modes validation
from genome4.seeds import PersonaNode       # has goals validation
from genome4.seeds import JourneyNode       # has steps, extract_node_name
from genome4.seeds import AgentNode         # has capabilities, before_work
from genome4.seeds import StoreNode         # has schema validation
from genome4.seeds import TestNode          # has run(), runnable property
from genome4.seeds import ConfigNode        # engine settings
```

Agents can also write `class MyNode(Node)` directly — no seed import required.

## CLI

```
genome4 check [path]         # validate, print tasks
genome4 converge [path]      # run convergence loop with agents
genome4 status [path]        # show status.yaml
genome4 init [path] --seed=X # initialize project with seed nodes
```

## What Makes This Different from genome3

| genome3 | genome4 |
|---------|---------|
| Templates are frozen infrastructure | Seed nodes are modifiable starting points |
| Agents can't modify templates | Agents modify anything they own |
| Predefined phases enforced | Phases are optional, agent-defined |
| Opinionated validation in templates | Agents write their own validate() |
| templates/ vs nodes/ directory split | Single plan/ directory |
| Engine has opinions (verb lists, etc.) | Engine is a dumb loop |
| Quality from template rules | Quality from agents checking their own work |

## Lessons from genome3

1. **Trust the agents.** They're as smart as you. Don't restrict their creative capacity.
2. **Agents will game bad checks.** If a validation rule is wrong, agents will hack around it instead of producing quality work. Fix the rule.
3. **Phase markers in doc, not knowledge.** Knowledge prunes to 8 entries. Doc is permanent.
4. **Parallel dispatch works.** Overlapping think time with serial apply. ~2x speedup, zero conflicts.
5. **Regression detection is essential.** Without it, agents can thrash (fix A, break B, fix B, break A).
6. **Git is the safety net.** Snapshot before, revert on regression. Simple and reliable.
7. **Load error tracking is critical.** Broken Python files must become visible tasks, not silent failures.
8. **Template shadow detection was wrong.** Instead of preventing agents from overriding templates, we should have let them improve the templates.
9. **The persona-as-service verb list was the biggest failure.** Opinionated engine logic caused mass false positives. Agents KNEW it was wrong but couldn't fix it. Engine should have no opinions.
10. **Holistic planning works.** One big task: "read the spec, plan everything." Agent decides when done. No hardcoded thresholds.

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│                 genome4                  │
│                                         │
│  ┌──────────┐  ┌──────────┐            │
│  │  Loader   │  │Validator │            │
│  │ (Python)  │→│(validate)│→ Tasks     │
│  └──────────┘  └──────────┘            │
│       ↑              │                  │
│       │              ↓                  │
│  plan/*.py      ┌─────────┐            │
│  (all nodes)    │ Router  │            │
│       ↑         │(owned_by)│            │
│       │         └────┬────┘            │
│       │              ↓                  │
│       │    ┌──────────────────┐        │
│       │    │  Agent Manager   │        │
│       │    │ (Claude Code x N)│        │
│       │    │ parallel dispatch │        │
│       │    └────────┬─────────┘        │
│       │             │                  │
│       │    ┌────────┴────────┐        │
│       │    │ Regression Guard │        │
│       │    │  (git snapshot)  │        │
│       │    └────────┬────────┘        │
│       │             │                  │
│       └─────────────┘                  │
│         (agents write nodes,           │
│          engine loops)                 │
└─────────────────────────────────────────┘
```

## File Structure (engine source)

```
genome4/
├── src/
│   ├── __init__.py         # exports Node, Task
│   ├── engine.py           # convergence loop
│   ├── loader.py           # load Python files from plan/
│   ├── validator.py        # universal checks only (load errors, dangling edges, staleness)
│   ├── agent_manager.py    # spawn/communicate with Claude Code processes
│   ├── regression.py       # detect regressions, manage git snapshots
│   ├── genome.py           # Genome class (graph of nodes)
│   └── node.py             # Node base class, Task class
├── seeds/
│   ├── complex-software/   # personas, services, journeys, depth checks
│   ├── simple-software/    # lighter version
│   └── blank/              # minimal starter
├── tests/                  # engine tests
├── BLUEPRINT.md            # this file
└── README.md
```
