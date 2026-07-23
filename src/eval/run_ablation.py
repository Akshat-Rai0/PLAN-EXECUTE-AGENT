"""
CLI entrypoint for the three-arm ablation study.

    python3 -m src.eval.run_ablation
    python3 -m src.eval.run_ablation --arms react plan_execute_full
    python3 -m src.eval.run_ablation --goals c1 c2 d1
    python3 -m src.eval.run_ablation --skip-judge   # metrics only, no LLM judge calls

WHAT THIS DOES NOT DO (read before treating output as final numbers):

1. Arm 2 (plan_execute_no_synthesis) is produced via a runtime monkey-
   patch, not a real code path that ships — see the detailed caveat in
   arm_runner.py's run_plan_execute_arm docstring. Treat Arm 2 numbers as
   a reasonable approximation of "what if synthesis didn't exist," not as
   a certification that the shipped agent has a working non-synthesis
   mode, because it doesn't.

2. category (e) browser_only goals are excluded from every run by default
   (no browser tool exists yet — see golden_dataset.py). The report says
   so explicitly rather than silently omitting them from a total count.

3. LLM-as-judge scores are exactly as reliable as the underlying judge
   LLM. For the 3 deterministic synthesis goals (d2/d3/d4) an exact-match
   check runs alongside the judge and both are reported — a mismatch
   between them is a signal to look at that specific run's raw output,
   not something this script resolves for you.

4. This makes real LLM API calls — one plan + N step calls per goal per
   arm, plus one judge call per goal (unless --skip-judge). Cost and time
   scale with (runnable goals) x (arms) x (LLM calls per run). Consider
   --goals to run a subset while developing/debugging this harness itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from src.eval.golden_dataset import GOLDEN_DATASET, GoldenGoal, runnable_goals, blocked_goals
from src.eval.arm_runner import ArmResult, run_plan_execute_arm, run_react_arm
from src.eval.judge import JudgeResult, judge_run

ALL_ARMS = ["react", "plan_execute_no_synthesis", "plan_execute_full"]


def _run_one_goal_one_arm(goal: GoldenGoal, arm: str) -> ArmResult:
    if arm == "react":
        return run_react_arm(goal_id=goal.id, goal=goal.goal)
    if arm == "plan_execute_no_synthesis":
        return run_plan_execute_arm(goal_id=goal.id, goal=goal.goal, disable_synthesis=True)
    if arm == "plan_execute_full":
        return run_plan_execute_arm(goal_id=goal.id, goal=goal.goal, disable_synthesis=False)
    raise ValueError(f"Unknown arm: {arm!r}")


def run_ablation(
    arms: list[str],
    goal_ids: Optional[list[str]] = None,
    skip_judge: bool = False,
    verbose: bool = True,
) -> dict:
    goals = runnable_goals()
    if goal_ids is not None:
        wanted = set(goal_ids)
        goals = [g for g in goals if g.id in wanted]
        missing = wanted - {g.id for g in goals}
        if missing:
            # Could be a typo, or a real (e) goal that's correctly excluded
            # — distinguish the two so the person isn't left guessing.
            blocked_ids = {g.id for g in blocked_goals()}
            for m in missing:
                if m in blocked_ids:
                    print(f"⚠️  Goal {m!r} was requested but is category (e) "
                          f"browser_only and not yet runnable — skipping it.")
                else:
                    print(f"⚠️  Goal {m!r} was requested but does not exist "
                          f"in the golden dataset — skipping it.")

    results: dict[str, dict[str, ArmResult]] = {g.id: {} for g in goals}
    judge_results: dict[str, dict[str, JudgeResult]] = {g.id: {} for g in goals}

    total_runs = len(goals) * len(arms)
    run_num = 0
    started_at = time.monotonic()

    for goal in goals:
        for arm in arms:
            run_num += 1
            if verbose:
                print(f"\n[{run_num}/{total_runs}] Running {arm!r} on {goal.id} ({goal.category})...")
                print(f"    Goal: {goal.goal}")

            t0 = time.monotonic()
            result = _run_one_goal_one_arm(goal, arm)
            elapsed = time.monotonic() - t0

            results[goal.id][arm] = result

            if verbose:
                status = "✅" if result.success else "❌"
                print(f"    {status} steps={result.step_count} "
                      f"replans={result.replan_count} "
                      f"synthesis={result.synthesis_count} "
                      f"approvals={result.approval_count} "
                      f"({elapsed:.1f}s)")
                if result.error:
                    print(f"    ⚠️  Error: {result.error.splitlines()[0]}")

            if not skip_judge and result.success and result.final_answer:
                jr = judge_run(goal, result.final_answer)
                judge_results[goal.id][arm] = jr
                if verbose:
                    if jr.judge_error:
                        print(f"    ⚠️  Judge error: {jr.judge_error}")
                    else:
                        em = "" if jr.exact_match_result is None else f" exact_match={jr.exact_match_result}"
                        print(f"    🧑‍⚖️  completeness={jr.completeness_score:.2f} "
                              f"correctness={jr.correctness_score:.2f}{em}")
            elif not skip_judge:
                # Run failed or produced no answer — record a zero-score
                # judge result rather than leaving a silent gap in the
                # report that would make aggregate averages ambiguous
                # about whether this goal was skipped or genuinely failed.
                judge_results[goal.id][arm] = JudgeResult(
                    goal_id=goal.id,
                    completeness_score=0.0,
                    correctness_score=0.0,
                    reasoning="Run did not succeed or produced no final answer — not sent to judge.",
                )

    total_elapsed = time.monotonic() - started_at

    return {
        "goals": goals,
        "arms": arms,
        "results": results,
        "judge_results": judge_results,
        "total_elapsed_seconds": total_elapsed,
        "skip_judge": skip_judge,
    }


def _aggregate_by_arm(run_output: dict) -> dict:
    """Compute per-arm aggregate metrics across all evaluated goals."""
    arms = run_output["arms"]
    results = run_output["results"]
    judge_results = run_output["judge_results"]
    goals = run_output["goals"]

    agg = {}
    for arm in arms:
        arm_results = [results[g.id][arm] for g in goals if arm in results[g.id]]
        succeeded = [r for r in arm_results if r.success]

        entry = {
            "total_goals": len(arm_results),
            "succeeded_runs": len(succeeded),
            "success_rate": len(succeeded) / len(arm_results) if arm_results else 0.0,
            "avg_step_count": mean([r.step_count for r in succeeded]) if succeeded else 0.0,
            "avg_replan_count": mean([r.replan_count for r in succeeded]) if succeeded else 0.0,
            "avg_synthesis_count": mean([r.synthesis_count for r in succeeded]) if succeeded else 0.0,
            "avg_wall_clock_seconds": mean([r.wall_clock_seconds for r in arm_results]) if arm_results else 0.0,
        }

        if not run_output["skip_judge"]:
            arm_judge_results = [
                judge_results[g.id][arm] for g in goals
                if arm in judge_results.get(g.id, {}) and judge_results[g.id][arm].judge_error is None
            ]
            entry["avg_completeness_score"] = (
                mean([j.completeness_score for j in arm_judge_results]) if arm_judge_results else 0.0
            )
            entry["avg_correctness_score"] = (
                mean([j.correctness_score for j in arm_judge_results]) if arm_judge_results else 0.0
            )

        agg[arm] = entry

    return agg


def _synthesis_isolation_check(run_output: dict) -> Optional[dict]:
    """
    The cleanest single number in the whole study (per the project spec):
    category (d) goals should fail on plan_execute_no_synthesis and
    succeed on plan_execute_full. Compute that comparison directly if
    both arms were run.
    """
    arms = run_output["arms"]
    if "plan_execute_no_synthesis" not in arms or "plan_execute_full" not in arms:
        return None

    results = run_output["results"]
    d_goals = [g for g in run_output["goals"] if g.category == "synthesis_required"]
    if not d_goals:
        return None

    no_synth_successes = sum(
        1 for g in d_goals
        if results[g.id].get("plan_execute_no_synthesis")
        and results[g.id]["plan_execute_no_synthesis"].success
        and results[g.id]["plan_execute_no_synthesis"].final_answer
    )
    full_successes = sum(
        1 for g in d_goals
        if results[g.id].get("plan_execute_full")
        and results[g.id]["plan_execute_full"].success
        and results[g.id]["plan_execute_full"].final_answer
    )

    return {
        "category_d_goal_count": len(d_goals),
        "no_synthesis_arm_successes": no_synth_successes,
        "full_arm_successes": full_successes,
        "coverage_gain": full_successes - no_synth_successes,
    }


def write_report(run_output: dict, output_dir: Path) -> tuple[Path, Path]:
    """Write both a machine-readable JSON report and a human-readable markdown summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    agg = _aggregate_by_arm(run_output)
    synthesis_check = _synthesis_isolation_check(run_output)

    # --- JSON report (full detail, machine-readable) ---
    json_data = {
        "timestamp_utc": timestamp,
        "arms_evaluated": run_output["arms"],
        "goals_evaluated": [g.id for g in run_output["goals"]],
        "blocked_goals_excluded": [g.id for g in blocked_goals()],
        "total_elapsed_seconds": run_output["total_elapsed_seconds"],
        "aggregate_by_arm": agg,
        "synthesis_isolation_check": synthesis_check,
        "per_goal_results": {
            goal_id: {
                arm: {
                    "success": r.success,
                    "step_count": r.step_count,
                    "replan_count": r.replan_count,
                    "synthesis_count": r.synthesis_count,
                    "approval_count": r.approval_count,
                    "wall_clock_seconds": r.wall_clock_seconds,
                    "final_answer": r.final_answer,
                    "error": r.error,
                    "judge": (
                        {
                            "completeness_score": run_output["judge_results"][goal_id][arm].completeness_score,
                            "correctness_score": run_output["judge_results"][goal_id][arm].correctness_score,
                            "reasoning": run_output["judge_results"][goal_id][arm].reasoning,
                            "judge_error": run_output["judge_results"][goal_id][arm].judge_error,
                            "exact_match_result": run_output["judge_results"][goal_id][arm].exact_match_result,
                        }
                        if arm in run_output["judge_results"].get(goal_id, {})
                        else None
                    ),
                }
                for arm, r in arm_results.items()
            }
            for goal_id, arm_results in run_output["results"].items()
        },
    }

    json_path = output_dir / f"ablation_report_{timestamp}.json"
    json_path.write_text(json.dumps(json_data, indent=2, default=str))

    # --- Markdown summary (human-readable) ---
    md_lines = [
        f"# Ablation Study Report — {timestamp}",
        "",
        f"Arms evaluated: {', '.join(run_output['arms'])}",
        f"Goals evaluated: {len(run_output['goals'])} "
        f"(of {len(GOLDEN_DATASET)} total in golden dataset; "
        f"{len(blocked_goals())} category-(e) browser goals excluded — no browser tool yet)",
        f"Total wall-clock time: {run_output['total_elapsed_seconds']:.1f}s",
        "",
        "## Aggregate metrics by arm",
        "",
        "| Arm | Success rate | Avg steps | Avg replans | Avg synthesis | Avg wall-clock (s) |"
        + ("" if run_output["skip_judge"] else " Avg completeness | Avg correctness |"),
        "|---|---|---|---|---|---|" + ("" if run_output["skip_judge"] else "---|---|"),
    ]
    for arm, a in agg.items():
        row = (
            f"| {arm} | {a['success_rate']:.0%} | {a['avg_step_count']:.1f} | "
            f"{a['avg_replan_count']:.1f} | {a['avg_synthesis_count']:.1f} | "
            f"{a['avg_wall_clock_seconds']:.1f} |"
        )
        if not run_output["skip_judge"]:
            row += f" {a['avg_completeness_score']:.2f} | {a['avg_correctness_score']:.2f} |"
        md_lines.append(row)

    md_lines.append("")

    if synthesis_check is not None:
        md_lines.extend([
            "## Synthesis isolation check (category d goals)",
            "",
            "Per the project spec, this is the cleanest single number in the "
            "whole study: category (d) goals need a tool not in the fixed "
            "registry, so they should fail without synthesis and succeed with it.",
            "",
            f"- Category (d) goals evaluated: {synthesis_check['category_d_goal_count']}",
            f"- Successes WITHOUT synthesis (Arm 2): {synthesis_check['no_synthesis_arm_successes']}",
            f"- Successes WITH synthesis (Arm 3): {synthesis_check['full_arm_successes']}",
            f"- **Coverage gain from synthesis: {synthesis_check['coverage_gain']} goals**",
            "",
        ])

    md_lines.extend([
        "## Caveats (read before citing these numbers)",
        "",
        "1. Arm 2 (`plan_execute_no_synthesis`) is produced via a runtime "
        "monkey-patch of the eval harness, not a real toggle in the shipped "
        "agent — see `arm_runner.py` docstring for details.",
        "2. Category (e) browser-only goals are excluded entirely — no "
        "browser automation tool exists in the codebase yet.",
        "3. LLM-as-judge scores depend on the judge LLM's own reliability. "
        "For deterministic goals (d2/d3/d4), cross-check the `exact_match` "
        "field in the JSON report against the judge's correctness_score — "
        "a mismatch means the judge got it wrong, not the agent.",
        "",
        f"Full per-goal, per-arm detail (including raw final answers and "
        f"judge reasoning) is in the accompanying JSON report: "
        f"`{json_path.name}`",
    ])

    md_path = output_dir / f"ablation_report_{timestamp}.md"
    md_path.write_text("\n".join(md_lines))

    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Run the three-arm ablation study.")
    parser.add_argument(
        "--arms", nargs="+", choices=ALL_ARMS, default=ALL_ARMS,
        help="Which arms to evaluate (default: all three).",
    )
    parser.add_argument(
        "--goals", nargs="+", default=None,
        help="Specific golden-dataset goal IDs to run (default: all runnable goals). "
             "Useful for a quick smoke test, e.g. --goals c1 d1.",
    )
    parser.add_argument(
        "--skip-judge", action="store_true",
        help="Skip LLM-as-judge scoring — just collect operational metrics "
             "(step/replan/synthesis counts, timing). Faster and cheaper "
             "for debugging the harness itself.",
    )
    parser.add_argument(
        "--output-dir", default="eval_results",
        help="Directory to write the JSON + markdown report to (default: eval_results/).",
    )
    args = parser.parse_args()

    print(f"Running ablation: arms={args.arms}, "
          f"goals={'all runnable' if args.goals is None else args.goals}, "
          f"skip_judge={args.skip_judge}")

    run_output = run_ablation(
        arms=args.arms,
        goal_ids=args.goals,
        skip_judge=args.skip_judge,
    )

    json_path, md_path = write_report(run_output, Path(args.output_dir))

    print(f"\n{'=' * 80}")
    print(f"Report written:")
    print(f"  JSON:     {json_path}")
    print(f"  Markdown: {md_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
