# GENOME5 — Hierarchical Agent Protocol

## 1. THE PROBLEM

AI agents produce shallow work when given broad tasks. Two root causes:

1. **Scope exceeds capacity.** "Plan a complex system" yields 22 use cases when 500 are needed. The agent spreads thin across the entire spec instead of going deep on each part.

2. **LLM sampling exhaustion.** Even on a focused task, an agent lists 6 items when 11 exist. Its token generation follows a sampling path — after 6 items, generation momentum pushes toward closure. Asking "what did you miss?" activates different attention patterns, finding 3 more. A fresh agent instance finds 2 more from different sampling paths. Multiple passes are needed to exhaust coverage.

An agent CAN produce 31 deeply-technical journey steps when focused on ONE flow. It CANNOT produce 500 comprehensive use cases when asked for "everything." And even on a focused task, it needs multiple passes to be truly comprehensive.

## 2. THE SOLUTION

Two mechanisms working together:

**A. Hierarchical decomposition.** Break every problem into levels where each level has 5-10 items. The agent handles 5-10 things at a time. The tree grows organically level by level.

**B. Iterative exhaustion.** At each level, the node's validate() lifecycle forces multiple passes: list children → create them → re-read spec and check for gaps → repeat until agent confirms nothing more to add → reviewer with fresh context checks again.

```
Level 0: Domains          (5-10 items)    ← agent reads FULL spec, identifies major areas
Level 1: Modules           (5-10 per domain) ← agent reads ONE spec section
Level 2: Services          (3-5 per module)  ← agent reads module description
Level 3: Use Cases         (5-10 per service) ← agent reads service + personas
Level 4: Journeys          (15-25 steps each) ← agent reads one use case
Level 5: Implementation    (source files)     ← agent reads journey as requirements
Level 6: Tests             (test cases)       ← agent reads use cases as test scenarios
```

At every level, scope is small AND multiple passes ensure comprehensive coverage. Depth is inevitable.

## 3. CORE CONCEPTS

### 3.1 Node

A Python file with hierarchical awareness:

```python
from genome5 import Node, Task

class GatewayModule(Node):
    name = "Gateway Module"
    type = "module"
    level = 1
    description = "HTTP edge layer — routing, rate limiting, SSE streaming"

    spec_reference = "docs/PANDO-PLAN.md:100-130"

    # EXACT node names — not descriptions. Agent creates children with these names.
    expected_children = [
        "Gateway API Service",
        "Rate Limiter Service",
        "SSE Stream Service",
        "Content Pre-Screen Service",
        "Auth Forwarding Service",
    ]
    children_verified = False  # set True after exhaustion passes

    edges = {
        "parent": "Infrastructure Domain",
        "owned_by": "Infrastructure Agent",
    }

    doc = "Gateway is the HTTP entry point. All requests flow through here."
    decisions = ["Chose SSE over WebSocket for build streaming — simpler, HTTP-native"]
    knowledge = []
```

### 3.2 Iterative Exhaustion Lifecycle

Planning nodes (Domain, Module, Service) go through a 4-state lifecycle. The validate() method drives the transitions. Each state is one engine cycle. Multiple cycles = multiple sampling passes.

```
STATE 1: expected_children is EMPTY
  → Task: "Read spec lines 100-130. List ALL child node names
           this section requires. Write them to expected_children."
  → Agent reads 30 lines of spec, lists 6 children.

STATE 2: expected_children EXISTS, some children MISSING
  → Task: "Create child node: 'Rate Limiter Service'
           (parent: Gateway Module, spec_reference: lines 108-112)"
  → Agent creates the child. One task per missing child.
  → Repeats until all listed children exist.

STATE 3: ALL listed children EXIST, children_verified is False
  → Task: "Re-read spec lines 100-130. Your expected_children
           lists 6 items. What concepts in the spec are NOT covered?
           Add any missing names to expected_children.
           If nothing is missing, set children_verified = True."
  → Agent re-reads with "what did I miss?" framing.
  → If it finds more: adds to expected_children → back to State 2.
  → If nothing more: sets children_verified = True → State 4.

STATE 4: children_verified is True
  → No more tasks from this node.
  → REVIEWER reads this node + spec → either approves or adds more
    expected_children (which resets children_verified → back to State 2).
```

**Why this works:**
- State 1 → State 3 forces the agent to re-read the spec after listing. Different framing = different sampling = finds more items.
- State 3 can loop back to State 2 multiple times. Each pass exhausts a different sampling path.
- State 4 → Reviewer provides a FRESH context (different agent instance) that catches systematic blind spots.
- Total passes: 3-5 per node before truly exhausted. Produces ~90% coverage vs ~60% from single pass.

**This only applies to PLANNING nodes.** Dev and test nodes have simpler lifecycles:

```python
# ServiceNode (dev phase) — NO exhaustion needed
# Tests catch bugs. One pass to write code.
class ServiceNode(Node):
    def validate(self, genome):
        for f in self.files:
            if not os.path.exists(f):
                return [Task(f"Implement: {f}")]  # just do it
        return []

# TestNode — NO exhaustion needed
# Binary: pass or fail. Engine runs tests.
class TestNode(Node):
    def validate(self, genome):
        if self.last_result.get("success") is False:
            return [Task("Fix failing test")]
        return []
```

### 3.3 Task

A message from validate() routed to the owning agent:

```python
class Task:
    message: str        # what needs fixing
    node_name: str      # which node has the problem
    phase: str          # planning, dev, test
    priority: int       # 1=highest
    severity: str       # error, warning, info
    check: str          # identifier for deduplication and cycle detection
    suggestion: str     # hint for the agent
```

### 3.4 Hierarchy

Nodes connect to parents via `edges = {"parent": "Parent Name"}`. Children are discovered by querying: "which nodes have parent = my name?"

```
Infrastructure Domain (Level 0)
  ├── parent: None (root)
  ├── children: Gateway Module, Hosting Module, P2P Module, ...
  │
  └── Gateway Module (Level 1)
       ├── parent: "Infrastructure Domain"
       ├── children: Gateway API Service, Rate Limiter Service, ...
       │
       └── Gateway API Service (Level 2)
            ├── parent: "Gateway Module"
            ├── children: Route Request UC, Handle Auth UC, ...
            │
            └── Route Request Use Case (Level 3)
                 ├── parent: "Gateway API Service"
                 └── journey: Route Request Journey (Level 4)
```

### 3.5 expected_children Matching

expected_children uses EXACT NODE NAMES, not fuzzy descriptions. The agent writes `expected_children = ["Rate Limiter Service"]` and creates a child node with `name = "Rate Limiter Service"`. The check is:

```python
existing_children = {n.name for n in self.children(genome)}
missing = [name for name in self.expected_children if name not in existing_children]
```

Binary match. No fuzzy logic. No keyword heuristics. If the agent wants to rename a child, it updates expected_children to match.

### 3.6 Cross-Cutting Nodes

Some nodes don't fit in one branch. Personas, security concerns, architecture decisions span multiple domains.

Solution: separate branches at Level 0:

```
Level 0 Domains:
  Infrastructure Domain
  Identity & Economics Domain
  Application Domain
  Security Domain
  Users Domain         ← personas live here
  Architecture Domain  ← cross-cutting decisions
```

Cross-cutting nodes REFERENCE nodes in other branches via edges:
```python
class ConsumerPersona(Node):
    edges = {
        "parent": "Users Domain",
        "uses": ["Gateway Module", "Marketplace Module", "App Store Module"],
    }
```

### 3.7 Review Nodes

At each level, a ReviewNode provides FRESH CONTEXT review:

```python
class Level1Review(Node):
    name = "Infrastructure Modules Review"
    type = "review"
    level = 1

    def validate(self, genome):
        # Only fire after all modules in this domain are children_verified
        domain = genome.get("Infrastructure Domain")
        modules = domain.children(genome)

        if not all(getattr(m, 'children_verified', False) for m in modules):
            return []  # wait for exhaustion to complete

        if not self._approved(genome):
            module_names = [m.name for m in modules]
            return [Task(
                f"FRESH REVIEW: Infrastructure has {len(modules)} modules: "
                f"{module_names}. Read the spec section for Infrastructure. "
                f"What modules are MISSING? If you find gaps, add them to "
                f"the domain's expected_children. If complete, approve.",
                self.name, phase="review", priority=2,
            )]
        return []
```

Review fires AFTER exhaustion (children_verified=True for all children at that level). The reviewer is a DIFFERENT agent with fresh sampling paths. It reads the spec + the node list and challenges.

Review at each level:
- Level 0: all spec domains covered (reads ~10 nodes)
- Level 1: all modules per domain (reads ~10 nodes per domain)
- Level 2: all services per module (reads ~10 nodes)
- Level 3: all use cases per service (reads ~10 nodes)
- No reviewer ever reads more than 50 nodes

## 4. ENGINE

### 4.1 Core Loop

Same as genome4: load → validate → route → fix → converge.

```python
while True:
    genome = load_all_nodes("plan/")
    tasks = validate_all(genome)

    if no tasks: CONVERGED

    top_task = prioritize(tasks)
    owner = find_owner(top_task)

    git_snapshot()
    result = assign_to_agent(owner, top_task)

    if regression: git_revert()
    else: git_commit()
```

The engine doesn't know about hierarchy, exhaustion, or reviews. It just runs validate() on every node, routes tasks, and loops. All the intelligence is in the NODES.

### 4.2 Level-Aware Prioritization

Level gating: only work on Level N+1 after Level N has 0 errors. This ensures top-down construction — domains exist and are reviewed before modules, modules before services.

```python
def _get_current_level(tasks, max_level=6):
    for level in range(max_level + 1):
        level_errors = [t for t in tasks
                        if t.priority <= level + 1 and t.severity == "error"]
        if level_errors:
            return level
    return None
```

Within a level, tasks are sorted by priority then severity.

### 4.3 Parallel Dispatch

Same as genome4: dispatch one task per distinct agent, apply serially. With domain agents owning separate branches, parallel dispatch is naturally effective — Infrastructure Agent and Identity Agent work on different branches simultaneously.

### 4.4 Cycle Detection

Track check IDs across cycles. If the same check fires → resolves → fires 3 times, skip it. Prevents infinite loops from poorly-written validate() methods.

### 4.5 Regression Guard

Git snapshot before agent work, revert if agent creates new critical errors without fixing the assigned task.

### 4.6 Crash Logging

Unhandled exceptions write to plan/engine-crash.log with full traceback.

## 5. AGENT ARCHITECTURE

### 5.1 Bootstrap

Engine creates HR Agent. HR Agent reads spec, creates:
1. Domain nodes (Level 0) with expected_children
2. Domain Agents (one per domain)
3. A Review Agent
4. Assigns domain ownership

### 5.2 Domain Agents

Each domain agent owns ONE branch of the hierarchy. It works top-down through the exhaustion lifecycle at each level:
1. Lists expected_children for its domain (Level 0) → creates module nodes
2. For each module: lists expected_children → creates service nodes
3. For each service: lists expected_children → creates use case nodes
4. For each use case: creates journey with steps

The agent reads 30-50 lines of spec per task. Creates 5-10 nodes per task. The exhaustion lifecycle re-asks "what did you miss?" at each level.

### 5.3 Review Agents

A review agent provides fresh-context challenge at each level. It fires AFTER exhaustion passes complete (children_verified=True). It reads all nodes at that level + the spec section and challenges:
- "The spec describes X but no module covers it"
- "This module has 3 services but the spec lists 5 capabilities"
- "Missing error scenarios for this service"

If the reviewer finds gaps, it adds to the parent's expected_children. This resets children_verified and triggers new child creation.

### 5.4 Cross-Cutting Agents

Special agents that span branches:
- **Security Agent**: reads ALL branches, adds threat scenarios, abuse cases
- **Architecture Agent**: reads ALL Level 1 modules, validates interfaces and connections

These agents create nodes in their own branches (Security Domain, Architecture Domain) with edges referencing nodes in other branches.

### 5.5 How Agents Learn the System

Three instruction layers, plus safety nets:

**Layer 1: System Prompt** (identity only)
```
"You are 'Infrastructure Agent'. [description].
Read ALL files listed in each task."
```

**Layer 2: Task Message** (state-specific instructions)
Each lifecycle state produces a task with SPECIFIC instructions for what to do:
- State 1: "Read spec lines X-Y. List ALL children as expected_children = ['Exact Name', ...]"
- State 2: "Create child node 'Rate Limiter Service' with parent='Gateway Module', level=2"
- State 3: "Re-read spec. Your list has N items. What's NOT covered? Add or set verified=True"

The validate() method writes these instructions. The agent follows the specific task.

**Layer 3: Agent Guide Seed** (examples + patterns)
The agent_guide.py seed node contains CONCRETE EXAMPLES for every lifecycle state:

```python
# Example: Creating a module node (State 2 output)
from genome5 import Node
class GatewayModule(Node):
    name = "Gateway Module"
    type = "module"
    level = 1
    spec_reference = "docs/PANDO-PLAN.md:100-130"
    expected_children = ["Gateway API Service", "Rate Limiter Service"]
    edges = {"parent": "Infrastructure Domain", "owned_by": "Infrastructure Agent"}
```

Examples are more powerful than abstract rules. Agent sees the pattern and follows it.

**Safety Nets** (engine catches mistakes):
- Wrong Python syntax → load error → P1 structural task
- Missing parent edge → dangling edge → structural task
- Wrong child name → expected_children check fails → task re-fires
- Missing name/description → base validate() catches it

Instructions reduce errors. Engine catches what agents get wrong.

### 5.6 Agent Self-Reflection

After every task, the agent prompt includes:
```
AFTER FIXING:
1. Update the node's knowledge with what you did
2. If you reference a node that doesn't exist, create the edge —
   the engine will detect the dangling edge and route a task to
   create the missing node.
3. If you discover something that changes the hierarchy,
   update expected_children on the parent node.
```

### 5.6 Discovery Flow

When deeper work reveals a missing branch:

```
Agent writing use cases for Gateway discovers:
  "Gateway needs to call a Notification Service for SSE events"
  ↓
Agent writes edge: calls "Notification Service"
Agent adds knowledge: "DISCOVERY: Need Notification Service
  under Infrastructure Domain"
  ↓
Engine detects: dangling edge to "Notification Service"
  ↓
Task fires → routes to Infrastructure Agent
  ↓
Infrastructure Agent adds "Notification Service" to
  Infrastructure Domain's expected_children
  ↓
Exhaustion lifecycle creates the new module
  ↓
New branch grows: module → services → use cases → journeys
```

The hierarchy grows ORGANICALLY. No one plans 10000 nodes upfront. Discoveries at deep levels propagate up via dangling edges, and new branches grow via the exhaustion lifecycle.

## 6. FULL LIFECYCLE

### 6.1 Planning Phase

```
STEP 1: HR Agent reads spec → creates Level 0 domains with expected_children
STEP 2: Exhaustion on Level 0 → re-read spec, add missing domains
STEP 3: Level 0 Review (fresh agent) → challenges domain coverage
STEP 4: Each Domain Agent creates Level 1 modules with expected_children
STEP 5: Exhaustion on Level 1 per domain → re-read, add missing modules
STEP 6: Level 1 Review per domain → challenges module coverage
STEP 7: Each Module gets Level 2 services with expected_children
STEP 8: Exhaustion on Level 2 → re-read, add missing services
STEP 9: Level 2 Review → challenges service coverage
STEP 10: Services get Level 3 use cases — happy path, error, edge, abuse
STEP 11: Exhaustion on Level 3 → re-read, add missing scenarios
STEP 12: Level 3 Review → challenges scenario coverage
STEP 13: Use cases get Level 4 journeys — step-by-step with failure points
STEP 14: Cross-cutting review — Security, Architecture agents
STEP 15: Final holistic review — senior agent reads Level 0+1 (~50 nodes)
```

Each level: list → create → exhaust → review → next level.
Total planning output: 500-2000+ nodes depending on project complexity.

### 6.2 Development Phase

The planning hierarchy IS the dev roadmap:

```
For each service (Level 2):
  - Read: service node + its use cases + its journeys
  - These ARE the requirements
  - Create: source files implementing the service
  - validate(): "do my files exist?"
```

Each service is ONE dev task. No exhaustion needed — tests catch bugs. Services develop in parallel across branches.

### 6.3 Testing Phase

Use cases ARE test scenarios:

```
For each use case (Level 3):
  - Read: use case + journey steps
  - Journey steps = test assertions
  - Create: TestNode with test_command
  - Engine runs test independently
  - Fail → task on the service → agent fixes code
  - Loop until all tests pass
```

### 6.4 Maintenance / Spec Changes

When the spec changes:
1. Affected domain node detects change (spec_reference lines modified)
2. Domain's validate() resets children_verified → exhaustion re-runs
3. Missing children → new tasks → agents create new branches
4. Changed children → staleness cascade within the branch
5. Other branches untouched (hierarchy isolates blast radius)

## 7. SEED SYSTEM

### 7.1 What Seeds Provide

Seeds are importable node types with built-in validate() lifecycles. NOT frozen. Agents modify freely.

```
seeds/complex-software/
  domain_node.py        # DomainNode — exhaustion lifecycle for modules
  module_node.py        # ModuleNode — exhaustion lifecycle for services
  service_node.py       # ServiceNode — exhaustion for use cases + file checks for dev
  use_case_node.py      # UseCaseNode — validates journey exists
  journey_node.py       # JourneyNode — validates steps with [ServiceName] refs
  test_node.py          # TestNode — runnable, test_command, run()
  review_node.py        # ReviewNode — fresh-context approval tracking
  agent_node.py         # AgentNode — capabilities, before_work, after_work
  config_node.py        # ConfigNode — engine settings
  agent_guide.py        # Knowledge node — how genome5 works
```

### 7.2 Seeds for Other Project Types

```
seeds/book/
  book_node.py          # BookNode → exhaustion lifecycle for acts
  act_node.py           # ActNode → exhaustion lifecycle for chapters
  chapter_node.py       # ChapterNode → exhaustion for scenes
  scene_node.py         # SceneNode → validates beats, dialogue, conflict
  character_node.py     # CharacterNode → validates arc, motivation, growth

seeds/legal/
  case_node.py          # CaseNode → exhaustion lifecycle for arguments
  argument_node.py      # ArgumentNode → exhaustion for evidence
  evidence_node.py      # EvidenceNode → validates source, relevance
```

The PATTERN (exhaustion lifecycle) is the same across project types. The NODE TYPES and HIERARCHY SHAPE change.

### 7.3 No Seed Required

Agents can write `class MyNode(Node)` with any hierarchy and any validate() lifecycle. Seeds just save time. A blank seed provides only the base Node class.

## 8. NODE BASE CLASS

```python
class Node:
    name: str = ""
    type: str = ""
    level: int = 0
    description: str = ""

    spec_reference: str = ""
    expected_children: list[str] = []   # EXACT child node names
    children_verified: bool = False     # True after exhaustion passes

    properties: dict = {}
    edges: dict = {}
    files: list[str] = []

    doc: str = ""
    decisions: list[str] = []
    knowledge: list[str] = []

    def validate(self, genome) -> list[Task]:
        tasks = []
        if not self.name:
            tasks.append(Task("Node has no name", phase="structural", priority=1))
        if not self.description:
            tasks.append(Task(f"'{self.name}': no description",
                         self.name, severity="warning"))
        return tasks

    def children(self, genome) -> list['Node']:
        return [n for n in genome.all_nodes()
                if n.edges.get("parent") == self.name]

    def parent_node(self, genome) -> 'Node | None':
        parent_name = self.edges.get("parent")
        return genome.get(parent_name) if parent_name else None

    def get_owner(self, genome) -> 'Node | None':
        owner_name = self.edges.get("owned_by")
        return genome.get(owner_name) if owner_name else None
```

## 9. PROJECT STRUCTURE

```
my-project/
  plan/                                 # agents organize however they want
    context.yaml                        # seed, spec reference, description
    hr_agent.py                         # bootstrapped by engine
    (agents create everything else)

  docs/
    spec.md                             # the spec / requirements

  src/                                  # created during dev phase
  tests/                               # created during test phase
```

The engine walks plan/ recursively. No required subdirectory structure. Agents organize files for clarity.

## 10. ENGINE SOURCE

```
genome5/
  src/
    node.py             # Node base class, Task class
    genome.py           # Genome graph + hierarchy helpers (children, parent)
    loader.py           # Load Python files from plan/, track errors, prune knowledge
    validator.py        # Universal checks: load errors, dangling edges, staleness (info-level)
    engine.py           # Convergence loop, level gating, parallel dispatch
    agent_manager.py    # Claude Code processes, NDJSON, timeout, dispatch IDs
    regression.py       # Regression detection, git snapshots
    cli.py              # CLI: check, converge, init, status

  seeds/
    complex-software/   # Software hierarchy with exhaustion lifecycles
    book/               # Book hierarchy
    blank/              # Just base Node

  tests/                # Engine tests
```

## 11. WHAT'S DIFFERENT FROM GENOME3/4

| Concept | genome3/4 | genome5 |
|---------|-----------|---------|
| Node structure | Flat | Hierarchical (parent → children) |
| Depth enforcement | count > 0 or "plan everything" | Exhaustion lifecycle: list → create → re-check → verify → review |
| Coverage per level | Single pass (60% coverage) | Multiple passes + fresh review (~90% coverage) |
| Task scope | "Plan everything" or fix one item | "List 5-10 children for THIS node from 30 lines of spec" |
| Agent scope | One agent for everything | Domain agents own branches |
| Review scope | One review of entire plan | Review per level, max 50 nodes each |
| expected_children | Not tracked | Exact node names, verified through lifecycle |
| Spec tracking | Read once holistically | spec_reference per node (30 lines) |
| Sampling exhaustion | Not addressed | Built into lifecycle (State 3 re-reads) |
| Fresh perspective | Same agent reviews own work | Reviewer is different agent instance |
| Planning → Dev | Weak connection | Hierarchy IS the roadmap |
| Planning → Test | Tests invented separately | Use cases ARE test scenarios |
| Discovery | Not supported | Dangling edges grow new branches |

## 12. LESSONS FROM GENOME3 AND GENOME4

1. **Flat nodes → shallow work.** Hierarchy forces depth at every level.
2. **"Plan everything" → surface coverage.** Small scope (30 lines) per task.
3. **Single pass → incomplete.** Multiple passes exhaust LLM sampling paths.
4. **Same brain reviewing → blind spots.** Fresh-context reviewer catches more.
5. **One agent doing everything → bottleneck.** Domain agents own branches, work in parallel.
6. **Frozen templates → can't self-heal.** Seed types are modifiable.
7. **validate() checking count > 0 → passes with 1 item.** expected_children lists exact names.
8. **Holistic review of 500 nodes → rubber stamp.** Level reviews of 10-50 nodes → thorough.
9. **Staleness loops → infinite cycles.** Cycle detection + staleness as info-level.
10. **Phase markers in knowledge → pruned.** Approvals in doc field (permanent).
11. **Agent marks "done" subjectively.** children_verified + reviewer = objective completion.

## 13. RESOLVED QUESTIONS

1. **expected_children matching** → EXACT node names. Binary match. No fuzzy logic.

2. **Level gating vs priority** → Level gating. Level N must have 0 errors before Level N+1 work begins. Safer, ensures top-down construction.

3. **How deep is deep enough?** → Planning: Level 4 (journeys). Dev: Level 5 (implementation). Test: Level 6. The hierarchy depth matches the project's natural structure.

4. **Cross-cutting cascade** → Cross-cutting agents (Security, Architecture) create nodes in their OWN branches with edges to other branches. They don't modify other agents' nodes. Staleness is limited to edge-based connections.

5. **Which tasks need exhaustion?** → The NODE TYPE decides. Planning nodes (Domain, Module, Service) have the exhaustion lifecycle in their seed validate(). Dev nodes (implementation) don't — tests catch bugs. Test nodes don't — binary pass/fail. The lifecycle is built into the seed type, not the engine.

## 14. VERIFICATION PLAN

1. Build engine + seeds with exhaustion lifecycle
2. Run on Pando spec — expect 500+ nodes with comprehensive use cases
3. Verify exhaustion works: after State 3, do expected_children grow?
4. Verify fresh review works: does reviewer find items the creator missed?
5. Compare to genome3 (291 nodes, 107 use cases) and genome4 (71 nodes, 22 use cases)
6. Spot-check quality at each level — are journeys deep? Are use cases comprehensive?
7. Run dev phase — do services get implemented from the plan?
8. Run test phase — do tests pass?
9. Simulate spec change — does only the affected branch update?
10. Test with a non-software project (book outline?) — does the hierarchy adapt?
