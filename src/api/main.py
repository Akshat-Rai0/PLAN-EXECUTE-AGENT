from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .event_bus import event_bus
from .models import CreateRunRequest, RunDetail, RunStepEvent, RunSummary, utc_now_iso
from .runner import execute_run_async, seed_from_agent_outputs
from .store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[2]
store = RunStore(REPO_ROOT / "run_visualizer.db")

app = FastAPI(title="Agent Run Visualizer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_active_tasks: dict[str, asyncio.Task] = {}


@app.on_event("startup")
async def startup() -> None:
    seed_from_agent_outputs(store, REPO_ROOT)


@app.get("/runs", response_model=list[RunSummary])
def list_runs() -> list[RunSummary]:
    return store.list_runs()


@app.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    detail = store.get_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return detail


@app.post("/runs", response_model=RunSummary)
async def create_run(body: CreateRunRequest) -> RunSummary:
    run_id = f"run-{uuid.uuid4().hex[:12]}"

    async def _run() -> None:
        await execute_run_async(run_id, body.task, body.arm, store, auto_approve=True)

    task = asyncio.create_task(_run())
    _active_tasks[run_id] = task
    task.add_done_callback(lambda _: _active_tasks.pop(run_id, None))

    detail = store.get_run(run_id)
    if detail:
        return RunSummary(
            run_id=detail.run_id,
            arm=detail.arm,
            task_name=detail.task_name,
            status=detail.status,
            duration_ms=detail.duration_ms,
            started_at=detail.started_at,
            pass_fail=detail.pass_fail,
        )
    return RunSummary(
        run_id=run_id,
        arm=body.arm,
        task_name=body.task[:120],
        status="running",
        duration_ms=None,
        started_at=utc_now_iso(),
        pass_fail=None,
    )


@app.websocket("/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    detail = store.get_run(run_id)
    if detail is None:
        await websocket.close(code=4404)
        return

    for step in detail.steps:
        await websocket.send_json(step.model_dump())

    if detail.status == "running":
        try:
            async for event in event_bus.subscribe(run_id):
                await websocket.send_json(event.model_dump())
        except WebSocketDisconnect:
            return
    else:
        await websocket.close()


frontend_dist = REPO_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
