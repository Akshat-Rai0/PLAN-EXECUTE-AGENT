# Plan-and-Execute Agent

A Plan-and-Execute agent with dynamic tool synthesis, benchmarked against a plain
ReAct baseline via a controlled three-arm ablation.

**Status:** early build — Stage 1 (fixed tool registry + ReAct baseline)

## Build stages
1. Fixed tool registry + ReAct loop (Arm 1 baseline) — in progress
2. Plan-and-Execute skeleton with replanning (Arm 2) — not started
3. Golden dataset (20 goals, categories a/b/c) — not started
4. Tool synthesis + category (d) goals (Arm 3) — not started
5. Human-in-the-loop approval gates — not started
6. Three-arm ablation + FastAPI/React frontend — not started

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

## To Test
```bash

% source .venv/bin/activate
python -m src.agents.plan_execute.main "Plan a weekend trip to Goa"

```