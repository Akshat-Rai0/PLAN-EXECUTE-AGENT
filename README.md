# Plan-and-Execute Agent

A Plan-and-Execute agent with dynamic tool synthesis, benchmarked against a plain
ReAct baseline via a controlled three-arm ablation.

**Status:** Phase 4 Complete — Dynamic Tool Synthesis ✅

## Build Progress
- **Phase 0** ✅ LangGraph & Tool-Calling Prereq
- **Phase 1** ✅ Planner + Step Schema  
- **Phase 2** ✅ Executor + Fixed Tool Layer
- **Phase 3** ✅ Replanner + Termination Logic (Arm 2 complete)
- **Phase 4** ✅ Dynamic Tool Synthesis
- **Phase 5** ✅ Sandbox Hardening
- **Phase 6** ⏳ Human-in-the-Loop Approval Gates
- **Phase 7** ⏳ Browser Automation (Arm 3 complete)
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
- `GROQ_API_KEY` - For Groq models (if using Groq as LLM provider)
- `LLM_PROVIDER` - Choose between "groq" (default) or "ollama" for local development
- `SANDBOX_TIMEOUT_SECONDS` - Code execution timeout (default: 15)
- `SANDBOX_MAX_MEMORY_MB` - Memory limit for sandboxed code (default: 256)
- `OUTBOUND_DOMAIN_ALLOWLIST` - Allowed domains for network access (default: api.tavily.com)

## Repo layout
```
src/
  tools/              fixed tool registry (search, code-exec, shell, file ops)
    registry.py       tool definitions and risk classification
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
  synthesis/          dynamic tool generation, validation, registration
    schema.py        SynthesisSchema and SynthesizedTool models
    codegen.py       LLM-driven schema declaration and code generation
    validator.py     sandbox validation for synthesized tools
    registry.py      tool registry for reuse across steps
  plans/              saved plans for debugging and analysis
  eval/               golden dataset, LLM-as-judge, ablation runner
frontend/             FastAPI + React (built last)
tests/
docs/
```

## Testing

The project includes comprehensive regression tests covering all LangGraph components:

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
