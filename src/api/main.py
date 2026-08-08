from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .event_bus import event_bus
from .models import ChatMessage, CreateRunRequest, InterruptResponse, RunDetail, RunStepEvent, RunSummary, utc_now_iso
from .runner import execute_run_async, get_interrupt_queues, seed_from_agent_outputs
from .store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[2]
store = RunStore(REPO_ROOT / "run_visualizer.db")

_active_tasks: dict[str, asyncio.Task] = {}
_active_chat_run: str | None = None  # Single active chat session guard


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    seed_from_agent_outputs(store, REPO_ROOT)
    yield
    # Shutdown
    # Cleanup any remaining tasks if needed
    for task_id, task in _active_tasks.items():
        if not task.done():
            task.cancel()
    _active_tasks.clear()


app = FastAPI(title="Agent Run Visualizer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    global _active_chat_run

    # Single-active-session guard: reject if a chat run is already active
    if _active_chat_run is not None:
        # Check if the active run is still running/waiting
        active_run = store.get_run(_active_chat_run)
        if active_run and active_run.status in ("running", "waiting_for_input"):
            raise HTTPException(
                status_code=409,
                detail=f"A chat run is already active. Please wait for run {_active_chat_run} to complete or switch to debugger mode."
            )
        else:
            # Previous run completed, clear the guard
            _active_chat_run = None

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    _active_chat_run = run_id  # Set as active chat run

    async def _run() -> None:
        try:
            await execute_run_async(run_id, body.task, body.arm, store)
        finally:
            # Clear active chat run when done
            global _active_chat_run
            if _active_chat_run == run_id:
                _active_chat_run = None

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


@app.post("/runs/{run_id}/interrupt")
async def respond_to_interrupt(run_id: str, response: InterruptResponse) -> dict[str, str]:
    """Submit human response to an interrupt waiting for input."""
    # Check if run exists
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Check if run is waiting for input
    if run.status != "waiting_for_input":
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is not waiting for input (current status: {run.status})"
        )

    # Check if interrupt queue exists for this run
    interrupt_queues = get_interrupt_queues()
    if run_id not in interrupt_queues:
        raise HTTPException(
            status_code=409,
            detail=f"No interrupt queue found for run {run_id}"
        )

    # Push response to the queue
    try:
        interrupt_queues[run_id].put(response.model_dump(exclude_none=True))
        return {"status": "submitted", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit response: {str(e)}")


@app.get("/runs/{run_id}/messages", response_model=list[ChatMessage])
def get_run_messages(run_id: str) -> list[ChatMessage]:
    """Retrieve chat message history for a run."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return store.get_messages(run_id)


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
