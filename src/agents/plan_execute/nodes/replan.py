"""Replanning and novelty-detection nodes."""

from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.prompts.loader import load_prompt
from ..state import State, StepStatus
from .common import _pkg

MAX_REPLAN = 8
MAX_TOTAL_STEPS = 15
MAX_CONSECUTIVE_IDENTICAL_REPLANS = 2


def _check_replan_novelty(previous_context: list[str], new_context: list[str]) -> tuple[bool, str]:
    """
    Use LLM to determine if new replan provides meaningful new information.
    
    Compares the previous step results with the new step results to detect
    whether the replan actually produced new, useful information or if it's
    essentially repeating the same search results.
    
    Returns (has_new_info, reason).
    """
    if not previous_context:
        # First replan always has new info by definition
        return True, "First replan - no previous context to compare"

    # Avoid a model call for the common retry case where execution supplied
    # exactly the same context as the prior replan.
    if previous_context == new_context:
        return False, "No new step results since the previous replan"
    
    previous_str = "\n".join(previous_context)
    new_str = "\n".join(new_context)
    
    # Truncate to keep the check fast and cheap
    previous_excerpt = previous_str[:3000]
    new_excerpt = new_str[:3000]
    
    novelty_prompt = load_prompt("plan_execute", "check_new_info").format(**locals())

    llm = _pkg().get_llm()
    messages = [
        SystemMessage(content=load_prompt("plan_execute", "check_new_info_system")),
        HumanMessage(content=novelty_prompt),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    has_new_info = True
    reason = ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("HAS_NEW_INFO:"):
            has_new_info = "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""

    if not reason:
        reason = "Could not determine novelty - assuming new information" if has_new_info else "No meaningful new information detected"

    return has_new_info, reason


def _detect_new_information(step_result: str, cumulative_context: list[str]) -> tuple[bool, str]:
    """
    Use LLM to determine if a single completed step's result contains
    substantially new information compared to all prior step results.

    This is used by check_new_info_node to decide whether to route to the
    replaner for optimisation after a successful step.

    Args:
        step_result: The result string of the just-completed step.
        cumulative_context: List of all prior step result strings accumulated
            in state["cumulative_context"].

    Returns (has_new_info, reason).
    """
    if not cumulative_context:
        # First completed step always has new info by definition — nothing to
        # compare against, and we don't want to replan after every first step,
        # so treat first step as NOT triggering a success replan.
        return False, "First step — no prior context to compare against"

    prior_str = "\n".join(cumulative_context)
    prior_excerpt = prior_str[:3000]
    step_excerpt = step_result[:2000]

    novelty_prompt = load_prompt("plan_execute", "replan_novelty").format(**locals())

    llm = _pkg().get_llm()
    messages = [
        SystemMessage(content=load_prompt("plan_execute", "replan_novelty_system")),
        HumanMessage(content=novelty_prompt),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    has_new_info = True
    reason = ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("HAS_NEW_INFO:"):
            has_new_info = "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""

    if not reason:
        reason = "Could not determine novelty — assuming new information" if has_new_info else "No meaningful new information detected"

    return has_new_info, reason


# Tool hints that can surface new knowledge and are worth checking for novelty.
# Write/delete/server steps never return new external information so we skip
# the LLM novelty call for them to save cost and latency.
_INFO_GATHERING_TOOL_HINTS = {
    "web_search", "tavily_search", "browser_use", "browser-use",
    "code_executor", "none", "synthesize_tool",
}


def check_new_info_node(state: State) -> dict:
    """
    Thin node inserted between every tool node and the post-tool routing
    decision. Evaluates whether the just-completed step's result contains
    new information that warrants replanning the remaining steps.

    Sets in state:
        last_step_new_info (bool): True if new info was detected.
        replan_reason (str): "success_new_info" or "failure" — read by replaner.
        cumulative_context (list[str]): Accumulates step results for future
            novelty comparisons (reducer appends, never overwrites).
    """
    plan = state["plan"]
    if plan is None:
        return {"last_step_new_info": False, "replan_reason": "failure"}

    # Find the step that just finished (DONE or FAILED).
    # executor_node sets a step to RUNNING then the tool node marks it DONE/FAILED.
    last_done = next(
        (s for s in reversed(plan.subtasks)
         if s.status in (StepStatus.DONE, StepStatus.FAILED)),
        None,
    )

    # If the step failed, signal failure routing immediately — no novelty check needed.
    if last_done is None or last_done.status == StepStatus.FAILED:
        return {
            "last_step_new_info": False,
            "replan_reason": "failure",
        }

    # Skip novelty detection for non-information-gathering steps (write, delete,
    # start_server, setup_workspace, shell_command) — they never return new
    # external knowledge.
    tool_hint = (last_done.tool_hint or "none").lower()
    if tool_hint not in _INFO_GATHERING_TOOL_HINTS:
        step_entry = f"Step {last_done.id}: {last_done.task}\nResult: {last_done.result or ''}"
        return {
            "last_step_new_info": False,
            "replan_reason": "failure",
            "cumulative_context": [step_entry],
        }

    step_result = last_done.result or ""
    step_entry = f"Step {last_done.id}: {last_done.task}\nResult: {step_result}"
    cumulative_context = state.get("cumulative_context") or []

    print(f"\n🔍 Checking for new information after step {last_done.id} ({tool_hint})...")
    has_new_info, reason = _pkg()._detect_new_information(step_result, cumulative_context)

    if has_new_info:
        print(f"  ✨ New information detected: {reason}")
    else:
        print(f"  ⏭️  No new information: {reason}")

    return {
        "last_step_new_info": has_new_info,
        "replan_reason": "success_new_info" if has_new_info else "failure",
        "cumulative_context": [step_entry],
    }


def replaner(state: State) -> dict:
    """
    Replan the remaining steps in the plan.

    This function is called either when:
    - A step fails (status=FAILED) — replan_reason="failure". Focuses on
      error recovery (finding a different approach to achieve the same goal).
    - A successful step reveals new information — replan_reason="success_new_info".
      Focuses on optimising/refining remaining steps using what was just learned.

    In both cases it preserves all DONE steps and only rewrites PENDING steps.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("replaner called with no plan in state")

    replan_reason = state.get("replan_reason") or "failure"
    reason_label = (
        "optimizing after new info" if replan_reason == "success_new_info"
        else "failure recovery"
    )

    print(f"\n{'='*80}")
    print(f"🔄 Replanning ({reason_label})")
    print(f"{'='*80}")

    # Check for consecutive identical replans - early termination
    consecutive_count = state.get("consecutive_identical_replans", 0)
    if consecutive_count >= MAX_CONSECUTIVE_IDENTICAL_REPLANS:
        print(f"❌ Consecutive identical replan limit reached ({MAX_CONSECUTIVE_IDENTICAL_REPLANS})")
        # Mark all remaining PENDING/RUNNING steps as CANCELLED
        cancelled_steps = [s for s in plan.subtasks if s.status in (StepStatus.PENDING, StepStatus.RUNNING)]
        for step in cancelled_steps:
            step.status = StepStatus.CANCELLED
            step.error = "Unable to find additional reliable information after multiple search attempts."
        plan.cancelled_steps.extend(cancelled_steps)
        # Remove cancelled steps from subtasks (filter by original status before we changed it)
        plan.subtasks = [s for s in plan.subtasks if s.status not in (StepStatus.CANCELLED,)]
        return {"plan": plan}

    # Check replan limit. `replan_count` accumulates via the sum_replan_count
    # reducer in state.py, so this reads the true total across all prior
    # replans, not just the delta from the last node call.
    current_replan_count = state.get("replan_count", 0)
    if current_replan_count >= MAX_REPLAN:
        print(f"❌ Replan limit reached ({MAX_REPLAN})")
        # Mark all remaining PENDING/RUNNING steps as CANCELLED instead of FAILED
        cancelled_steps = [s for s in plan.subtasks if s.status in (StepStatus.PENDING, StepStatus.RUNNING)]
        for step in cancelled_steps:
            step.status = StepStatus.CANCELLED
            step.error = f"Replan limit ({MAX_REPLAN}) exceeded - execution terminated"
        plan.cancelled_steps.extend(cancelled_steps)
        # Remove cancelled steps from subtasks (filter by original status before we changed it)
        plan.subtasks = [s for s in plan.subtasks if s.status not in (StepStatus.CANCELLED,)]
        return {"plan": plan}
    else:
        # Collect the results of completed steps — this reflects what actually
        # EXECUTED so far in this run (i.e. the outcome of the previous replan
        # cycle, if any).
        completed_results = []
        done_steps = []
        for step in plan.subtasks:
            if step.status == StepStatus.DONE:
                done_steps.append(step)
                if step.result:
                    completed_results.append(f"Step {step.id}: {step.task}\nResult: {step.result}")
            elif step.status == StepStatus.FAILED and step.error:
                completed_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

        # Compare THIS replan's incoming context (what execution has produced so
        # far) against what was on hand at the time of the LAST replan. This is
        # the correct comparison — real outcomes vs. real outcomes.
        #
        # Previously this compared `completed_results` against the results of the
        # brand-new plan `breakdown_task` was about to generate — but a
        # freshly-generated plan is always all-PENDING and has never executed, so
        # that comparison was structurally guaranteed to find "no new info" every
        # single time, regardless of whether the replan was actually repetitive.
        # That caused premature termination after just one real replan cycle.
        # Bound before novelty comparison as well as before planning. This
        # makes identical large results comparable without another model call.
        completed_results = _pkg().bound_replan_context(completed_results)

        previous_context = state.get("last_replan_context")
        if previous_context is None:
            # No prior replan cycle to compare against yet (this is the first
            # replan in the run) — nothing to judge novelty against.
            has_new_info, novelty_reason = True, "First replan - no previous context to compare"
        else:
            has_new_info, novelty_reason = _pkg()._check_replan_novelty(previous_context, completed_results)

        # Generate a new plan based on the original goal and the results of completed steps.
        new_plan = _pkg().breakdown_task(plan.goal, context=completed_results, replan_reason=replan_reason)

        # Merge DONE steps back to preserve execution history and results for synthesis
        next_id = 1
        if done_steps:
            done_steps.sort(key=lambda s: s.id)
            for s in done_steps:
                s.id = next_id
                next_id += 1

        for s in new_plan.subtasks:
            s.id = next_id
            next_id += 1

        new_plan.subtasks = done_steps + new_plan.subtasks

        print(f"✅ New plan generated with {len(new_plan.subtasks)} steps ({reason_label})")
        if not has_new_info:
            print(f"⚠️  No new information found (consecutive: {consecutive_count + 1})")

        # Return the delta only — do not mutate `state` directly. LangGraph applies
        # the registered reducers (see state.py) to whatever this dict returns;
        # writing to `state` in place bypasses that and can cause inconsistent
        # results when nodes run concurrently or the graph replays from a checkpoint.
        if has_new_info:
            # Reset consecutive counter when we have new information
            return {
                "plan": new_plan,
                "replan_count": 1,
                "consecutive_identical_replans": 0,
                "last_replan_context": completed_results,
            }
        else:
            # Increment consecutive counter when no new information. The reducer
            # now REPLACES rather than accumulates, so we must compute the new
            # value explicitly here rather than returning a delta of 1.
            return {
                "plan": new_plan,
                "replan_count": 1,
                "consecutive_identical_replans": consecutive_count + 1,
                "last_replan_context": completed_results,
            }
