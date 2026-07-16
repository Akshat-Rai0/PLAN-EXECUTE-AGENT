# Plan-and-Execute Agent

A Plan-and-Execute agent with dynamic tool synthesis, benchmarked against a plain
ReAct baseline via a controlled three-arm ablation.

**Status:** Phase 3 Complete — Arm 2 (Plan-and-Execute with replanning) ✅

## Build Progress
- **Phase 0** ✅ LangGraph & Tool-Calling Prereq
- **Phase 1** ✅ Planner + Step Schema  
- **Phase 2** ✅ Executor + Fixed Tool Layer
- **Phase 3** ✅ Replanner + Termination Logic (Arm 2 complete)
- **Phase 4** ⏳ Dynamic Tool Synthesis
- **Phase 5** ⏳ Sandbox Hardening
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
cp .env.example .env  # add your API keys
```

## Repo layout
```
src/
  tools/            fixed tool registry (search, code-exec, etc.)
  sandbox/           subprocess sandbox: timeouts, resource caps, allowlisting
  agents/
    react/           Arm 1 — plain ReAct loop
    plan_execute/     Arm 2/3 — LangGraph planner/executor/replanner
  synthesis/          dynamic tool generation, validation, registration
  eval/               golden dataset, LLM-as-judge, ablation runner
frontend/             FastAPI + React (built last)
tests/
docs/
```

## Testing

The project includes comprehensive regression tests covering all LangGraph components:

### Test Coverage (50 tests total)
- **test_routing.py** (8 tests) - Graph conditional edge routing logic
- **test_reason_node.py** (7 tests) - Reasoning node execution and context handling  
- **test_tavily_search_node.py** (12 tests) - Search node and context extraction
- **test_replaner.py** (8 tests) - Replaner logic and state management
- **test_synthesize_node.py** (10 tests) - Synthesis node final answer generation
- **test_e2e_graph.py** (5 tests) - End-to-end graph execution flows

### Running Tests
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_routing.py -v

# Run with coverage
python3 -m pytest tests/ --cov=src --cov-report=html
```

### Regression Bugs Covered
Tests specifically target and validate fixes for production bugs:
- **Premature-synthesis bug** - `tool_hint="none"` steps no longer short-circuit to synthesis
- **Silent-stub bug** - Reasoning steps get real LLM calls instead of silent no-ops
- **Reducer bug** - `replan_count` correctly accumulates across multiple replans
- **Silent-discard bug** - `synthesize_node` writes to `plan.final_answer` correctly
- **Context inclusion bugs** - Prior step results properly included in reasoning prompts
- **Search context bugs** - Years extracted from prior results, long results not folded in

## To Test
```bash
% source .venv/bin/activate
python -m src.agents.plan_execute.main "Plan a weekend trip to Goa"
```