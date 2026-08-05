# Plan-and-Execute Agent

A Plan-and-Execute agent with dynamic tool synthesis, benchmarked against a plain
ReAct baseline via a controlled three-arm ablation.

**Status:** Phase 7 Complete — Browser Automation with Vision ✅

## Build Progress
- **Phase 0** ✅ LangGraph & Tool-Calling Prereq
- **Phase 1** ✅ Planner + Step Schema
- **Phase 2** ✅ Executor + Fixed Tool Layer
- **Phase 3** ✅ Replanner + Termination Logic (Arm 2 complete)
- **Phase 4** ✅ Dynamic Tool Synthesis
- **Phase 5** ✅ Sandbox Hardening
- **Phase 6** ✅ Human-in-the-Loop Approval Gates
- **Phase 7** ✅ Browser Automation (Vision capabilities with OpenRouter Gemma integration)
- **Phase 8** ⏳ ReAct Baseline + Ablation (Arm 1)
- **Phase 9** ⏳ Web UI + Deployment

## Architecture
- [Project spec](docs/plan-and-execute-agent.html) — problem definition, scope, stack, timeline, risks
- [System wiring](docs/system-wiring.html) — step-by-step flows and wire diagrams for every subsystem

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys (ANTHROPIC_API_KEY, TAVILY_API_KEY, GROQ_API_KEY)
```

Required environment variables:
- `ANTHROPIC_API_KEY` - For Claude models (if using Claude as LLM provider)
- `TAVILY_API_KEY` - For web search functionality
- `GROQ_API_KEY` - Required when `LLM_PROVIDER=groq` (for tool-calling model)
- `OPENROUTER_API_KEY` - Required for the default agentic model (Nemotron via OpenRouter) and for Browser Use web-automation steps (Gemma via OpenRouter)
- `LLM_PROVIDER` - Choose between "openrouter" (default), "groq", "anthropic", or "ollama"
- `SANDBOX_TIMEOUT_SECONDS` - Code execution timeout (default: 15)
- `SANDBOX_MAX_MEMORY_MB` - Memory limit for sandboxed code (default: 256)
- `OUTBOUND_DOMAIN_ALLOWLIST` - Allowed domains for network access (default: api.tavily.com)

### Browser Use

Browser steps use `OPENROUTER_API_KEY` and require the local browser runtime after
dependencies are installed:

```bash
browser-use install
```

The graph uses `tool_hint="browser_use"` for rendered-page tasks and runs
`google/gemma-4-26b-a4b-it:free` through OpenRouter with vision enabled. The Plan-and-Execute
agent uses `nvidia/nemotron-3-ultra-550b-a55b:free` through OpenRouter by
default. Browser actions are approval-gated as HIGH-risk operations; the system
automatically detects and requests approval for form submissions, purchases,
account changes, messages, or other external side effects.

Browser Use Configuration:
- Model: `google/gemma-4-26b-a4b-it:free` (supports structured outputs)
- Max steps: 25 (configurable via `BROWSER_USE_MAX_STEPS`)
- Max failures: 3 (configurable via `BROWSER_USE_MAX_FAILURES`)
- Vision: Enabled for rendered page analysis
- Approval: Required for all browser operations (HIGH-risk classification)

## Tool Definitions and Usage Guidelines

The agent uses a sophisticated tool routing system with clear risk classifications and specific use cases for each tool.

### Available Tools

#### LOW-RISK TOOLS (Safe Operations)
- **`tavily_search` / `web_search`** - Read-only web search for information retrieval
  - Use when: You need current information, facts, or data from the internet
  - When to prefer: Always first choice for information gathering before considering other tools
  - Risk level: LOW (read-only)

- **`today_date`** - System date read
  - Use when: You need the current date for time-sensitive queries
  - When to prefer: Automatically injected for recency-anchored queries
  - Risk level: LOW (read-only)

- **`reason` / `none`** - Pure LLM reasoning without external tools
  - Use when: The task requires analysis, planning, or synthesis of existing information
  - When to prefer: When you have all necessary context and just need to process it
  - Risk level: LOW (pure computation)

- **`setup_workspace`** - Directory creation for project workspaces
  - Use when: Starting any coding or file-based task
  - When to prefer: Always as the first step for app/coding tasks
  - Risk level: LOW (limited scope directory creation)

#### HIGH-RISK TOOLS (Require Approval)
- **`shell_command`** - Execute CLI commands (npm, git, mkdir, etc.)
  - Use when: You need to run development commands, package managers, or system tools
  - When to prefer: For scaffolding, dependency installation, git operations
  - Safety note: `rm` is blocked - use `delete_file` instead
  - Risk level: HIGH (can execute arbitrary commands)

- **`write_file` / `file_editor`** - Write or edit source code files
  - Use when: Creating or modifying source code, configuration files, or documentation
  - When to prefer: After workspace setup, for implementing features
  - Risk level: HIGH (can write arbitrary files)

- **`delete_file`** - Delete files or directories in workspace
  - Use when: Cleaning up, removing files, or clearing workspace
  - When to prefer: For any deletion task (never use shell rm)
  - Risk level: HIGH (destructive operation)

- **`code_executor`** - Execute Python code with full Python standard library
  - Use when: One-off calculations, data processing, or computational tasks
  - When to prefer: For single-use computations that don't need to be reused
  - Risk level: HIGH (can execute arbitrary Python code)

- **`synthesize_tool`** - Dynamically generate reusable Python tools
  - Use when: You need a custom capability not in the fixed tool registry
  - When to prefer: When the same logic needs to be applied to multiple inputs
  - Risk level: HIGH (generates and executes new code at runtime)

- **`start_server`** - Start development servers (npm run dev, python http.server, etc.)
  - Use when: Running web applications or APIs for testing
  - When to prefer: As the final step of app-building tasks
  - Risk level: HIGH (can start network services)

- **`browser_use`** - Browser automation for rendered UI interaction
  - Use when: Navigating websites, filling forms, or interacting with live UI
  - When to prefer: When web_search cannot perform the required task (rendered content needed)
  - Risk level: HIGH (can interact with third-party websites)

### Tool Selection Guidelines

1. **Start with LOW-RISK tools** - Always prefer read-only operations first
2. **Use approval gating** - HIGH-RISK tools require human confirmation before execution
3. **Consider reusability** - Use `synthesize_tool` for logic that will be reused across multiple steps
4. **Prefer `code_executor` for one-offs** - Single calculations should use code_executor, not synthesis
5. **Never use shell rm** - Always use `delete_file` for any deletion operations
6. **Browser as last resort** - Only use `browser_use` when web_search cannot accomplish the task

## Performance Optimization Recommendations

### Token Cost Reduction Strategies

1. **Context Window Optimization**
   - The system automatically truncates long context using smart truncation (head + tail)
   - Replan context is bounded to 12,000 characters max to prevent runaway token growth
   - Search results are filtered to remove noise (navigation bars, footers, ads)

2. **Smart Tool Selection**
   - Use `today_date` directly instead of searching for current date
   - Prefer specific searches over broad queries to reduce irrelevant results
   - Use `reason` for analysis when all needed context is already available

3. **Caching and Reuse**
   - Synthesized tools are cached in the registry for reuse across steps
   - Date anchors are pre-pended to avoid redundant date lookups
   - Search context from prior steps is intelligently folded into subsequent queries

4. **Efficient LLM Usage**
   - Two-step synthesis (declare schema → generate code) reduces wasted tokens
   - Temperature set to 0 for deterministic outputs where appropriate
   - Short, focused prompts for validation checks rather than full reasoning

### Output Speed Improvements

1. **Parallel Execution Opportunities**
   - Consider implementing parallel step execution for independent tasks
   - Background browser operations could run concurrently with other steps

2. **Streaming and Incremental Results**
   - Implement streaming responses for long-running operations
   - Show incremental progress during multi-step plans

3. **Model Selection Strategy**
   - Use faster models for routine tasks (date, simple reasoning)
   - Reserve powerful models for complex synthesis and browser tasks
   - Current setup uses OpenRouter's free models for cost efficiency

4. **Timeout and Resource Management**
   - Configurable sandbox timeouts (default: 15 seconds)
   - Memory limits for code execution (default: 256MB)
   - Network allowlisting to prevent hanging on unreachable domains

5. **Smart Caching**
   - Cache search results for identical queries within a session
   - Reuse synthesized tools across steps with same capability needs
   - Persistent user information store to avoid repeated prompts

### Recommended Environment Variables for Optimization

```bash
# Sandbox limits for faster failure detection
SANDBOX_TIMEOUT_SECONDS=10  # Reduce from 15 for faster feedback
SANDBOX_MAX_MEMORY_MB=128  # Reduce from 256 for memory-constrained environments

# Search optimization
TAVILY_MAX_RESULTS=3  # Keep minimal for faster searches
TAVILY_SEARCH_DEPTH=basic  # Use basic unless advanced needed

# Browser use limits
BROWSER_USE_MAX_STEPS=20  # Reduce from 25 for quicker completion
BROWSER_USE_MAX_FAILURES=2  # Reduce from 3 for faster fallback

# Development settings
VALIDATE_SEARCH_RELEVANCE=false  # Disable for production speed (enable for quality)
```

## Repo layout
```
src/
  tools/              fixed tool registry (search, code-exec, shell, file ops)
    registry.py       tool definitions and risk classification
    browser_use/      Browser Use runner (OpenRouter Gemma, vision-enabled)
      config.py       Browser configuration and model settings
      runner.py       Async browser task execution
      free_openrouter.py  OpenRouter adapter for free models
  sandbox/            subprocess sandbox: timeouts, resource caps, network guards
    runner.py         sandbox execution with output validation
    shell_runner.py   shell command execution with allowlisting
    network_guard.py  network access controls
    server_manager.py dev server management
  agents/
    react/            Arm 1 — plain ReAct loop
    plan_execute/    Arm 2/3 — LangGraph planner/executor/replanner
      graph.py       LangGraph wiring and routing
      nodes.py       planner, executor, replanner, synthesis nodes
      state.py       state schema and step status tracking
      tools.py       tool integration and context building
      llm.py         LLM provider abstraction
      main.py        CLI entry point with interrupt handling
  synthesis/          dynamic tool generation, validation, registration
    schema.py        SynthesisSchema and SynthesizedTool models
    codegen.py       LLM-driven schema declaration and code generation
    validator.py     sandbox validation for synthesized tools
    registry.py      tool registry for reuse across steps
  plans/              saved plans for debugging and analysis
  eval/               golden dataset, LLM-as-judge, ablation runner
    golden_dataset.py  Test cases including browser use scenarios
frontend/             FastAPI + React (built last)
tests/
docs/
```

## Testing

The project includes comprehensive regression tests covering all LangGraph components and a golden dataset for system evaluation.

### Test Coverage (136 tests total)
- **test_routing.py** - Graph conditional edge routing logic
- **test_reason_node.py** (7 tests) - Reasoning node execution and context handling  
- **test_tavily_search_node.py** (12 tests) - Search node and context extraction
- **test_replaner.py** (10 tests) - Replaner logic and state management
- **test_synthesize_node.py** (10 tests) - Synthesis node final answer generation
- **test_e2e_graph.py** - End-to-end graph execution flows
- **test_code_executor_node.py** (9 tests) - Code execution node with sandbox
- **test_output_store.py** (3 tests) - Output persistence and workspace management
- **test_performance_guards.py** (3 tests) - Performance and resource limits
- **test_plan_execute.py** - Plan-and-Execute integration tests
- **test_replan_novelty_and_date_anchor.py** (33 tests) - Replan novelty detection
- **test_replan_query_narrowing.py** (4 tests) - Query narrowing during replanning
- **test_risk_classifier.py** (5 tests) - Risk assessment and classification
- **test_sandbox_network_guard.py** (11 tests) - Network access controls
- **test_sandbox_runner.py** (12 tests) - Sandbox execution environment
- **test_sqlite_checkpointer.py** (3 tests) - State persistence with SQLite
- **test_synthesis.py** (8 tests) - Dynamic tool synthesis
- **test_tavily_recency_params.py** (6 tests) - Search recency parameter handling
- **test_tavily_search.py** - Tavily search integration

### Golden Dataset (28 goals for system evaluation)

The golden dataset provides comprehensive test cases for evaluating agent performance across different categories:

**Categories:**
- **forced_replan** (5 goals) - Tests replanning behavior when steps fail
- **new_information** (5 goals) - Tests handling of new information that changes the plan
- **straightforward** (5 goals) - Baseline efficiency tests without replanning
- **synthesis_required** (5 goals) - Tests dynamic tool synthesis capabilities
- **browser_required** (8 goals) - Tests browser automation with vision capabilities

**Browser Test Goals:**
- Google Travel flights search with form filling
- Basic page content extraction from example.com
- Weather website search with temperature extraction
- GitHub trending repositories navigation
- Reddit programming feed extraction
- Amazon product search and data extraction
- Hacker News ranking identification
- Complex multi-step Wikipedia navigation

**Stress Tests (1 per category):**
- **forced_replan**: Multiple consecutive failure handling
- **new_information**: Long dependency chain across 5 searches
- **straightforward**: Complex multi-step computation on single result set
- **synthesis_required**: Tool synthesis, reuse, and computational accuracy
- **browser_required**: Complex multi-step browser workflow with navigation

Run the golden dataset summary:
```bash
python3 src/eval/golden_dataset.py
```

### Running Tests
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_routing.py -v

# Run with coverage
python3 -m pytest tests/ --cov=src --cov-report=html
```

## Agent outputs

Every completed Plan-and-Execute or ReAct CLI run is persisted under the
repository-root `agent_outputs/` directory using a labelled folder such as
`20260718-134500_what-is-a-llm/`.

```
agent_outputs/<timestamp>_<goal>/
  summary.md       concise final answer and step index
  plan.json        complete Plan-and-Execute plan and raw tool output
  react-trace.json complete ReAct turn history and raw observations
  workspace/       generated source code and Markdown files, when applicable
```

The execution workspace remains temporary and sandboxed. Dependency/cache
directories such as `node_modules/` are not copied; generated deliverables are.

### Regression Bugs Covered
Tests specifically target and validate fixes for production bugs:
- **Premature-synthesis bug** - `tool_hint="none"` steps no longer short-circuit to synthesis
- **Silent-stub bug** - Reasoning steps get real LLM calls instead of silent no-ops
- **Reducer bug** - `replan_count` correctly accumulates across multiple replans
- **Silent-discard bug** - `synthesize_node` writes to `plan.final_answer` correctly
- **Context inclusion bugs** - Prior step results properly included in reasoning prompts
- **Search context bugs** - Years extracted from prior results, long results not folded in
- **Replan limit bug** - Steps never executed when replan limit exceeded are marked as SKIPPED instead of FAILED
- **Synthesis registry bug** - Missing `registry.py` module added for tool reuse across steps
- **Sandbox network guard** - Network access controls properly enforced during code execution

## To Test
```bash
% source .venv/bin/activate
python -m src.agents.plan_execute.main "Plan a weekend trip to Goa"
```

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Akshat-Rai0/PLAN-EXECUTE-AGENT)
