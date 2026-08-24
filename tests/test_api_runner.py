from src.agents.plan_execute.state import Plan, Step, StepStatus
from src.api.runner import RunTracker
from src.api.store import RunStore


def test_tracker_streams_pydantic_plan_steps(tmp_path):
    """Live LangGraph updates use Pydantic models, not replay dictionaries."""
    store = RunStore(tmp_path / "runs.db")
    store.create_run("run-live", "plan_execute_synthesis", "test task")
    tracker = RunTracker("run-live", "plan_execute_synthesis", store)
    plan = Plan(
        goal="test task",
        subtasks=[Step(id=1, task="Research the answer", tool_hint="tavily_search")],
    )

    tracker.update_from_state({"plan": plan, "replan_count": 0}, "plan")
    plan.subtasks[0].status = StepStatus.RUNNING
    tracker.update_from_state({"plan": plan, "replan_count": 0}, "executor")
    plan.subtasks[0].status = StepStatus.DONE
    plan.subtasks[0].result = "Research result"
    tracker.update_from_state({"plan": plan, "replan_count": 0}, "tavily_search")

    steps = {step.step_id: step for step in store.get_run("run-live").steps}
    assert steps["run-live-plan"].status == "success"
    assert steps["run-live-step-1"].status == "success"
    assert steps["run-live-step-1"].payload.result == "Research result"


def test_tracker_still_supports_dictionary_steps(tmp_path):
    store = RunStore(tmp_path / "runs.db")
    store.create_run("run-replay", "plan_execute_synthesis", "test task")
    tracker = RunTracker("run-replay", "plan_execute_synthesis", store)

    tracker.update_from_state(
        {
            "plan": {
                "goal": "test task",
                "subtasks": [
                    {
                        "id": 1,
                        "task": "Research the answer",
                        "tool_hint": "tavily_search",
                        "status": "DONE",
                        "result": "Research result",
                    }
                ],
            },
            "replan_count": 0,
        },
        "tavily_search",
    )

    steps = {step.step_id: step for step in store.get_run("run-replay").steps}
    assert steps["run-replay-step-1"].status == "success"
