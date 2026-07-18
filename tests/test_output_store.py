from datetime import datetime

from src.agents.plan_execute.output_store import persist_react_run_artifacts, persist_run_artifacts
from src.agents.react.state import Turn
from src.agents.plan_execute.state import Plan, Step, StepStatus


def test_persist_run_artifacts_copies_generated_workspace_and_metadata(tmp_path):
    workspace = tmp_path / "temporary-workspace"
    generated_markdown = workspace / "src" / "what-is-llm.md"
    generated_markdown.parent.mkdir(parents=True)
    generated_markdown.write_text("# What is an LLM?\n", encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "dependency.js").write_text("ignored", encoding="utf-8")

    plan = Plan(
        goal="What is an LLM?",
        final_answer="An LLM is a language model.",
        subtasks=[
            Step(
                id=1,
                task="Write a Markdown explanation",
                tool_hint="write_file",
                status=StepStatus.DONE,
                result="Wrote src/what-is-llm.md",
            )
        ],
    )

    run_dir = persist_run_artifacts(
        repo_root=tmp_path,
        plan=plan,
        workspace_path=str(workspace),
        started_at=datetime(2026, 7, 18, 13, 45, 0),
    )

    assert run_dir == tmp_path / "agent_outputs" / "20260718-134500_what-is-an-llm"
    assert (run_dir / "plan.json").is_file()
    assert '"goal": "What is an LLM?"' in (run_dir / "plan.json").read_text(encoding="utf-8")
    assert (run_dir / "summary.md").read_text(encoding="utf-8").startswith("# Agent run: What is an LLM?")
    assert (run_dir / "workspace" / "src" / "what-is-llm.md").read_text(encoding="utf-8") == "# What is an LLM?\n"
    assert not (run_dir / "workspace" / "node_modules").exists()


def test_persist_run_artifacts_records_research_run_without_workspace(tmp_path):
    plan = Plan(
        goal="What is today's date?",
        final_answer="The current date is 2026-07-18.",
        subtasks=[
            Step(id=1, task="Determine the date", status=StepStatus.DONE, result="2026-07-18")
        ],
    )

    run_dir = persist_run_artifacts(
        repo_root=tmp_path,
        plan=plan,
        started_at=datetime(2026, 7, 18, 13, 46, 0),
    )

    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "No generated workspace files" in summary
    assert not (run_dir / "workspace").exists()


def test_persist_react_run_artifacts_uses_the_shared_output_directory(tmp_path):
    run_dir = persist_react_run_artifacts(
        repo_root=tmp_path,
        goal="What is an LLM?",
        final_answer="An LLM generates language.",
        iterations=3,
        history=[
            Turn(
                thought="Find a definition",
                action="web_search",
                action_input="LLM definition",
                observation="An LLM is a language model.",
            )
        ],
        started_at=datetime(2026, 7, 18, 13, 47, 0),
    )

    assert run_dir == tmp_path / "agent_outputs" / "20260718-134700_what-is-an-llm"
    assert (run_dir / "react-trace.json").is_file()
    assert '"agent": "react"' in (run_dir / "react-trace.json").read_text(encoding="utf-8")
    assert "Total iterations (LLM calls): 3" in (run_dir / "summary.md").read_text(encoding="utf-8")
