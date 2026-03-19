# GENOME5 — Hierarchical Agent Protocol

## 1. THE PROBLEM

AI agents produce shallow work when given broad tasks. "Plan a complex system" yields 22 use cases when 500 are needed. The agent reads the spec, creates surface-level output, marks "done." No amount of prompt engineering, template rules, or convergence loops fixes this because the ROOT cause is: **the task scope exceeds the agent's capacity for comprehensive coverage.**

An agent CAN produce 31 deeply-technical journey steps when focused on ONE flow. It CANNOT produce 500 comprehensive use cases when asked for "everything."

## 2. THE SOLUTION

**Hierarchical decomposition.** Break every problem into levels where each level has 5-10 items. The agent handles 5-10 things comprehensively. The tree grows organically level by level. Total depth is massive (1000s of nodes) but no single task asks for more than 10 items.

```
Level 0: Domains          (5-10 items)    ← agent reads FULL spec, identifies major areas
Level 1: Modules           (5-10 per domain) ← agent reads ONE spec section
Level 2: Services          (3-5 per module)  ← agent reads module description
Level 3: Use Cases         (5-10 per service) ← agent reads service + personas
Level 4: Journeys          (15-25 steps each) ← agent reads one use case
Level 5: Implementation    (source files)     ← agent reads journey as requirements
Level 6: Tests             (test cases)       ← agent reads use cases as test scenarios
```

At every level, the agent's scope is small and focused. Depth is INEVITABLE because each level demands the next.

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

    spec_reference = "docs/PANDO-PLAN.md:100-130"  # which spec lines this covers

    expected_children = [
        "API routing and request dispatch",
        "Rate limiting and DDoS protection",
        "Server-Sent Events streaming",
        "Content pre-screening integration",
        "Authentication token forwarding",
    ]

    edges = {
        "parent": "Infrastructure Domain",
        "owned_by": "Infrastructure Agent",
    }

    doc = "Gateway is the HTTP entry point. All requests flow through here."
    decisions = ["Chose SSE over WebSocket for build streaming — simpler, HTTP-native"]
    knowledge = ["Created from spec lines 100-130. 5 expected children identified."]

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        # Check each expected child exists
        my_children = [n for n in genome.all_nodes()
                       if n.edges.get("parent") == self.name]
        child_descriptions = " ".join(c.description.lower() for c in my_children)

        for expected in self.expected_children:
            # Fuzzy check: is this concept covered by any child?
            keywords = expected.lower().split()
            if not any(kw in child_descriptions for kw in keywords[:2]):
                tasks.append(Task(
                    f"'{self.name}' expects child covering '{expected}' but none found. "
                    f"Read {self.spec_reference} and create the missing node.",
                    self.name, phase="planning", priority=2,
                    check=f"missing-child-{expected[:20]}",
                ))

        return tasks
```

### 3.2 Task

Same as genome4 — a message from validate() routed to the owning agent:

```python
class Task:
    message: str        # what needs fixing
    node_name: str      # which node has the problem
    phase: str          # planning, dev, test
    priority: int       # 1=highest (also used for level ordering)
    severity: str       # error, warning, info
    check: str          # identifier for deduplication and cycle detection
    suggestion: str     # hint for the agent
```

### 3.3 Hierarchy

Nodes connect to parents via `edges = {"parent": "Parent Name"}`. Children are discovered by querying: "which nodes have parent = my name?"

```
Infrastructure Domain (Level 0)
  ├── parent: None (root)
  ├── children: Gateway Module, Hosting Module, P2P Module, ...
  │
  └── Gateway Module (Level 1)
       ├── parent: "Infrastructure Domain"
       ├── children: API Service, Rate Limiter, SSE Service, ...
       │
       └── API Service (Level 2)
            ├── parent: "Gateway Module"
            ├── children: Route Request UC, Handle Auth UC, ...
            │
            └── Route Request Use Case (Level 3)
                 ├── parent: "API Service"
                 └── journey: Route Request Journey (Level 4)
```

### 3.4 Cross-Cutting Nodes

Some nodes don't fit in one branch. Personas, security concerns, architecture decisions span multiple domains.

Solution: a separate "cross-cutting" branch at Level 0:

```
Level 0 Domains:
  Infrastructure Domain
  Identity & Economics Domain
  Application Domain
  Security Domain
  Users Domain         ← personas live here
  Architecture Domain  ← cross-cutting architecture decisions
```

Cross-cutting nodes REFERENCE nodes in other branches via edges:
```python
class ConsumerPersona(Node):
    edges = {
        "parent": "Users Domain",
        "uses": ["Gateway Module", "Marketplace Module", "App Store Module"],
    }
```

### 3.5 Review Nodes

At each level, a ReviewNode checks comprehensiveness:

```python
class Level0Review(Node):
    name = "Domain Coverage Review"
    type = "review"
    level = 0

    def validate(self, genome):
        tasks = []
        domains = [n for n in genome.all_nodes() if n.level == 0 and n.type == "domain"]

        # Read spec and check if all major areas are covered
        # (Agent reads spec + domain list and challenges)
        if not self._all_approved(genome):
            tasks.append(Task(
                f"Review Level 0: {len(domains)} domains exist. Read the full spec. "
                f"Are ALL major areas covered? Missing anything? "
                f"Approve by adding 'Level 0 approved' to your doc.",
                self.name, phase="review", priority=1,
            ))
        return tasks
```

Review at each level ensures:
- Level 0: all spec domains covered (reads ~10 nodes)
- Level 1: all modules in each domain (reads ~10 nodes per domain)
- Level 2: all services in each module (reads ~10 nodes)
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

    top_task = prioritize(tasks)  # sorts by level, then priority
    owner = find_owner(top_task)

    git_snapshot()
    result = assign_to_agent(owner, top_task)

    if regression: git_revert()
    else: git_commit()
```

### 4.2 Level-Aware Prioritization

Tasks are sorted: Level 0 before Level 1 before Level 2. Within a level, by priority. This ensures top-down construction — domains exist before modules, modules before services.

```python
def prioritize(tasks):
    return sorted(tasks, key=lambda t: (
        phase_order.get(t.phase, 99),
        t.priority,  # level maps to priority (L0=P1, L1=P2, etc.)
        severity_order.get(t.severity, 3),
    ))
```

Alternatively, use explicit level gating: only work on Level N+1 after Level N has 0 errors.

### 4.3 Parallel Dispatch

Same as genome4: dispatch one task per distinct agent, apply serially. With domain agents owning separate branches, parallel dispatch is naturally effective — Infrastructure Agent and Identity Agent work on different branches simultaneously.

### 4.4 Cycle Detection

Same as genome4: track check IDs across cycles. If the same check fires → resolves → fires 3 times, skip it. Prevents infinite loops from poorly-written validate() methods.

### 4.5 Regression Guard

Same as genome4: git snapshot before agent work, revert if agent creates new critical errors without fixing the assigned task.

### 4.6 Crash Logging

Same as genome4: unhandled exceptions write to plan/engine-crash.log with full traceback.

## 5. AGENT ARCHITECTURE

### 5.1 Bootstrap

Engine creates HR Agent. HR Agent reads spec, creates:
1. Domain Agents (one per Level 0 domain)
2. A Level 0 Review Agent
3. Assigns domain ownership

### 5.2 Domain Agents

Each domain agent owns ONE branch of the hierarchy. It reads its spec section and works top-down:
1. Creates module nodes (Level 1) with expected_children
2. Creates service nodes (Level 2) with expected_children
3. Creates use case nodes (Level 3) with journey expectations
4. Creates journey nodes (Level 4) with detailed steps

The agent is FOCUSED — it only reads 30-50 lines of spec per task, only creates 5-10 nodes per task.

### 5.3 Review Agents

At each level, a review agent reads all nodes at that level and challenges:
- "The spec describes X but no domain covers it"
- "This module has 2 services but the spec describes 5 capabilities"
- "This use case is missing error scenarios"

Review agents at each level ensure nothing is skipped. They approve each level before the next level begins.

### 5.4 Cross-Cutting Agents

Special agents that span branches:
- **Security Agent**: reads ALL branches, adds threat scenarios, abuse cases
- **Architecture Agent**: reads ALL Level 1 modules, validates interfaces and connections
- **Integration Agent**: ensures modules connect properly (API contracts, data flow)

These agents have READ access to the full tree but WRITE only to their own nodes (security nodes, architecture decision nodes, integration nodes).

### 5.5 Agent Self-Reflection

After every task, the agent prompt includes:
```
AFTER FIXING:
1. Update the node's knowledge with what you did
2. REFLECT: Should you update expected_children?
   Did you discover something that changes the hierarchy?
   Should a new branch be created?
3. If you reference a node that doesn't exist, create the edge —
   the engine will detect the gap and grow a new branch.
```

## 6. FULL LIFECYCLE

### 6.1 Planning Phase

```
STEP 1: HR Agent reads spec → creates 4-6 Domain Agents + domains
STEP 2: Level 0 Review → "all domains covered?"
STEP 3: Each Domain Agent creates modules (Level 1) with expected_children
STEP 4: Level 1 Review per domain → "all modules covered?"
STEP 5: Each module gets services (Level 2) with expected_children
STEP 6: Level 2 Review → "all services covered?"
STEP 7: Services get use cases (Level 3) — happy path, error, edge, abuse
STEP 8: Level 3 Review → "all scenarios covered?"
STEP 9: Use cases get journeys (Level 4) — step-by-step with failure points
STEP 10: Cross-cutting review — Security, Architecture, Integration agents
STEP 11: Final holistic review — senior agent reads Level 0+1 (50 nodes)
```

Each step gates the next. Review agents approve before deeper work begins. Total planning output: 500-2000+ nodes depending on project complexity.

### 6.2 Development Phase

The planning hierarchy IS the dev roadmap:

```
For each service (Level 2):
  - Read: service node + its use cases + its journeys
  - These ARE the requirements
  - Create: source files implementing the service
  - validate(): "do my files exist? do they compile?"
```

Each service is ONE dev task. Agent reads 10-20 nodes (service + children) and writes code. Focused. Specific. No guessing what to build.

Services can be developed in parallel — different agents work on different services simultaneously (parallel dispatch).

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

The engine's TestNode.run() executes tests via subprocess. Results are trustworthy — agents can't fake them.

### 6.4 Maintenance / Spec Changes

When the spec changes:
1. Affected domain node detects change (spec_reference lines modified)
2. Domain's validate() re-checks expected_children against updated spec
3. Missing children → new tasks → agents create new branches
4. Changed children → staleness cascade within the branch
5. Other branches untouched (hierarchy isolates blast radius)

## 7. SEED SYSTEM

### 7.1 What Seeds Provide

Seeds are importable node types with pre-built validate() logic. NOT frozen. Agents modify freely.

```
seeds/complex-software/
  domain_node.py        # DomainNode — validates modules exist
  module_node.py        # ModuleNode — validates services exist
  service_node.py       # ServiceNode — validates use cases + files exist
  use_case_node.py      # UseCaseNode — validates journey exists
  journey_node.py       # JourneyNode — validates steps + [ServiceName] refs
  test_node.py          # TestNode — runnable, test_command, run()
  review_node.py        # ReviewNode — approval tracking
  agent_node.py         # AgentNode — capabilities, before_work, after_work
  config_node.py        # ConfigNode — engine settings
  agent_guide.py        # Knowledge node — how genome5 works
  planning_workflow.py  # Workflow node — level-gated planning sequence
```

### 7.2 Seeds for Other Project Types

```
seeds/book/
  book_node.py          # BookNode → validates acts exist
  act_node.py           # ActNode → validates chapters exist
  chapter_node.py       # ChapterNode → validates scenes exist
  scene_node.py         # SceneNode → validates beats, dialogue, conflict
  character_node.py     # CharacterNode → validates arc, motivation, growth

seeds/legal/
  case_node.py          # CaseNode → validates arguments exist
  argument_node.py      # ArgumentNode → validates evidence, precedents
  evidence_node.py      # EvidenceNode → validates source, relevance
```

### 7.3 No Seed Required

Agents can write `class MyNode(Node)` with any hierarchy. Seeds just save time. A blank seed provides only the base Node class — agents build everything from scratch.

## 8. NODE BASE CLASS

```python
class Node:
    name: str = ""
    type: str = ""
    level: int = 0          # hierarchy level (0=root, 1=child, etc.)
    description: str = ""

    spec_reference: str = ""          # which spec lines this covers
    expected_children: list[str] = [] # what children should exist

    properties: dict = {}
    edges: dict = {}        # parent, owned_by, depends_on, calls, etc.
    files: list[str] = []   # source files (dev phase)

    doc: str = ""                     # PERMANENT: what this node IS
    decisions: list[str] = []        # PERMANENT: why choices were made
    knowledge: list[str] = []        # PRUNABLE: work history (last 8)

    def validate(self, genome) -> list[Task]:
        """Base validation. Seed types add hierarchy checks."""
        tasks = []
        if not self.name:
            tasks.append(Task("Node has no name", phase="structural", priority=1))
        if not self.description:
            tasks.append(Task(f"'{self.name}': no description",
                         self.name, severity="warning"))
        return tasks

    def children(self, genome) -> list['Node']:
        """Get all nodes whose parent edge points to this node."""
        return [n for n in genome.all_nodes()
                if n.edges.get("parent") == self.name]

    def parent_node(self, genome) -> 'Node | None':
        """Get this node's parent."""
        parent_name = self.edges.get("parent")
        return genome.get(parent_name) if parent_name else None

    def get_owner(self, genome) -> 'Node | None':
        owner_name = self.edges.get("owned_by")
        return genome.get(owner_name) if owner_name else None
```

## 9. PROJECT STRUCTURE

```
my-project/
  plan/
    context.yaml                    # seed, spec reference, project description
    hr_agent.py                     # bootstrapped by engine

    # Agents create everything below:
    domains/
      infrastructure.py             # DomainNode (Level 0)
      identity_economics.py
      application.py
      security.py
      users.py

    modules/
      gateway.py                    # ModuleNode (Level 1)
      hosting.py
      p2p.py
      auth.py
      ledger.py
      ...

    services/
      gateway_api.py                # ServiceNode (Level 2)
      rate_limiter.py
      sse_stream.py
      ...

    use_cases/
      route_request.py              # UseCaseNode (Level 3)
      rate_exceeded.py
      ddos_attack.py
      ...

    journeys/
      route_request_journey.py      # JourneyNode (Level 4)
      ...

    agents/
      infrastructure_agent.py
      identity_agent.py
      security_agent.py
      review_agent.py
      ...

    reviews/
      level0_review.py
      level1_infrastructure_review.py
      ...

  docs/
    PANDO-PLAN.md                   # the spec

  src/                              # created during dev phase
    gateway/
      api.ts
      rate_limiter.ts
      ...

  tests/                            # created during test phase
    gateway/
      route_request.test.ts
      ...
```

Agents organize files however they want. The engine walks plan/ recursively. Subdirectories are optional — agents create them for clarity.

## 10. ENGINE ARCHITECTURE

```
genome5/
  src/
    node.py             # Node base class, Task class
    genome.py           # Genome graph (nodes + hierarchy helpers)
    loader.py           # Load Python files from plan/, track errors
    validator.py        # Universal checks: load errors, dangling edges, staleness
    engine.py           # Convergence loop, parallel dispatch, level ordering
    agent_manager.py    # Claude Code process management, NDJSON, timeout
    regression.py       # Regression detection, git snapshots
    cli.py              # CLI: check, converge, init, status

  seeds/
    complex-software/   # Software project hierarchy types
    book/               # Book project hierarchy types
    legal/              # Legal project hierarchy types
    blank/              # Just base Node — agents build everything

  tests/                # Engine tests
```

## 11. WHAT'S DIFFERENT FROM GENOME4

| Concept | genome4 | genome5 |
|---------|---------|---------|
| Node structure | Flat (all nodes at same level) | Hierarchical (parent → children) |
| Depth enforcement | validate() checks count > 0 | expected_children from spec section |
| Task scope | "Plan everything" | "Create 5-10 children for THIS node" |
| Agent scope | One agent handles everything | Domain agents own branches |
| Review | One holistic review of everything | Review at each level (max 50 nodes) |
| Quality gate | Subjective ("agent marks done") | Objective (all expected_children exist) |
| Spec tracking | Spec read once holistically | spec_reference per node (30 lines each) |
| Scale | Breaks at ~100 nodes | Works at any depth (5-10 items per task) |
| Planning → Dev | Separate phases, weak connection | Hierarchy IS the dev roadmap |
| Planning → Test | Separate phases, tests invented | Use cases ARE test scenarios |

## 12. LESSONS FROM GENOME3 AND GENOME4

1. **Flat nodes → shallow work.** The hierarchy forces depth at every level.
2. **"Plan everything" → surface coverage.** Each task is 5-10 items from 30 lines of spec.
3. **One agent doing everything → bottleneck.** Domain agents own branches, work in parallel.
4. **Frozen templates → agents can't self-heal.** Seed types are modifiable.
5. **validate() checking count > 0 → passes with 1 shallow item.** expected_children lists specific items.
6. **Holistic review of 500 nodes → rubber stamp.** Level reviews of 10-50 nodes → thorough.
7. **Staleness loops → infinite cycles.** Cycle detection skips recurring checks.
8. **Phase markers in knowledge → pruned away.** Approvals in doc field (permanent).
9. **mtime-based staleness as error → blocks progress.** Staleness as info (advisory).
10. **Same brain reviewing own work → blind spots.** Cross-cutting agents bring different perspectives.

## 13. OPEN QUESTIONS

1. **expected_children fuzzy matching** — how precisely does validate() check if a concept is covered? Keyword matching is fragile. Agent judgment is subjective. Need a balance.

2. **Level gating vs priority ordering** — should Level 1 be BLOCKED until Level 0 review approves? Or just lower priority? Blocking is safer but slower.

3. **How deep is deep enough?** — should we have Level 5, 6, 7? Or is Level 4 (journeys) the natural bottom for planning? The hierarchy can go as deep as needed but there's a point of diminishing returns.

4. **Cross-cutting cascade** — Security Agent adds threat scenarios across ALL domains. How many nodes does it touch? If it modifies 50 nodes in one pass, that's a lot of staleness. Manageable?

5. **Agent model selection** — should domain agents be cheaper models (Sonnet) for mechanical decomposition, and review agents be expensive (Opus) for judgment? Or all Opus?

## 14. VERIFICATION PLAN

1. Build engine + seeds
2. Run on Pando spec — expect 500+ nodes with deep use cases and journeys
3. Spot-check quality at each level — are expected_children comprehensive?
4. Compare to genome3 (291 nodes) and genome4 (71 nodes) — must be deeper
5. Run dev phase — do services get implemented from the plan?
6. Run test phase — do tests pass?
7. Simulate spec change — does only the affected branch update?
8. Test with a non-software project (book outline?) — does the hierarchy adapt?
