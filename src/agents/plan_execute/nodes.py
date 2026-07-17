import re
from datetime import date

from .state import State, StepStatus, Step, Plan
from .tools import breakdown_task
from src.tools.registry import tavily_search, today_date
from langchain_core.messages import HumanMessage, SystemMessage
from .llm import get_llm

# Matches a plausible 4-digit year (1900-2099). Used to pull a year mentioned
# in a prior reasoning step (e.g. "The current year is 2026.") forward into a
# later search query, since search relevance depends heavily on the query
# text itself — a correct fact determined in an earlier step does nothing for
# retrieval quality unless it's actually present in the words being searched.
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Above this length, a prior step's result is almost certainly a raw scraped
# search result (noisy, long, full of boilerplate) rather than a short
# reasoning-step conclusion. We don't want to feed that kind of text into a
# new search query — long, noisy queries tend to return WORSE results, not
# better. Short results (like a one-line date fact from reason_node) are safe
# to fold in directly.
_SHORT_RESULT_CHAR_LIMIT = 200


def _extract_search_context(plan, current_step) -> str:
    """
    Build a short, targeted context string from the most recent prior DONE
    step, to append to this step's search query.

    Only looks at the single most recent prior step (not all of them) and
    only uses its result if it's short — i.e. looks like a reasoning-step
    conclusion (e.g. "The current year is 2026.") rather than a raw scraped
    search result. This deliberately does NOT concatenate every prior
    result — that would bloat the query with noise and degrade search
    relevance rather than improve it.

    Additionally, scans ALL prior DONE step results (short or long) for a
    plausible year, since a correctly-determined year is the single most
    common piece of context a later search needs (see: "who won world cup
    this year" — the year is what search needs, not the surrounding prose).
    """
    prior_done_steps = [
        s for s in plan.subtasks
        if s.id != current_step.id and s.status == StepStatus.DONE and s.result
    ]
    # Only steps that come before this one in the plan
    prior_done_steps = [s for s in prior_done_steps if s.id < current_step.id]
    if not prior_done_steps:
        return ""

    context_parts = []

    # 1. Most recent short prior result — folded in directly.
    most_recent = max(prior_done_steps, key=lambda s: s.id)
    if len(most_recent.result) <= _SHORT_RESULT_CHAR_LIMIT:
        context_parts.append(most_recent.result.strip())

    # 2. Any year mentioned in ANY prior DONE step — surfaced explicitly.
    # Search separately from (1) since the year might be buried in a step
    # that isn't the most recent one, or in a result too long to fold in
    # directly.
    detected_years = []
    for step in prior_done_steps:
        for match in _YEAR_PATTERN.finditer(step.result):
            detected_years.append(match.group())
    if detected_years:
        # Prefer the year from the most recent step if it appears in the
        # detected set; otherwise just take the most recently detected one.
        year = detected_years[-1]
        if year not in " ".join(context_parts):
            context_parts.append(year)

    return " ".join(context_parts)


# Words/phrases that signal a goal is asking about something time-relative —
# "latest", "recent", "current", "this year", etc. For these goals, knowing
# today's actual date is load-bearing for every downstream search (see: "who
# won the world cup this year" defaulting to 2022 because nothing in the
# pipeline was anchored to the real current date). Rather than relying on the
# LLM planner to remember to add a "determine the current date" step — which
# it does inconsistently — we detect this deterministically from the goal
# text and prepend a real date step every time, guaranteed, before the plan
# is even generated.
#
# NOTE: "todays?" (with an optional trailing s, no apostrophe needed) covers
# both "today's date" and the common typed form "todays date" — \btoday\b
# alone does NOT match "todays", since there's no word boundary between the
# "y" and the "s" (both are word characters), which was the original bug:
# "whats todays date ?" went completely undetected and fell through to a full
# unnecessary web search instead of using today_date() directly.
_RECENCY_KEYWORDS = re.compile(
    r"\b(latest|recent(?:ly)?|current(?:ly)?|now|todays?|this year|this month|"
    r"this week|so far|up[- ]to[- ]date|as of|ongoing|most recent)\b",
    re.IGNORECASE,
)

# Goals that are PURELY asking for the current date/day/time — as opposed to
# goals that merely reference recency in passing while asking about something
# else (e.g. "who won the world cup this year"). For these, planning and
# searching is pure waste: the whole goal is answered by a single
# today_date() call. Matched narrowly on purpose — this should only catch
# goals where the date genuinely IS the entire question, not just a
# component of a larger one.
_PURE_DATE_QUERY = re.compile(
    r"^\s*(what'?s?|whats|what is|tell me|give me)?\s*"
    r"(today'?s?|the current|current)\s*(date|day)\s*\??\s*$",
    re.IGNORECASE,
)


def _is_pure_date_query(goal: str) -> bool:
    """Return True if the goal is asking ONLY for today's date/day, with
    nothing else — in which case planning and searching are unnecessary."""
    return bool(_PURE_DATE_QUERY.match(goal.strip()))


def _needs_date_anchor(goal: str) -> bool:
    """Return True if the goal contains recency language that needs today's
    actual date resolved before anything else runs."""
    return bool(_RECENCY_KEYWORDS.search(goal))


def _make_date_anchor_step(next_id: int) -> Step:
    """
    Build a deterministic first step that calls today_date() directly —
    no LLM call, no search, just the real system date — and prepend it to
    the plan. Marked DONE immediately since there's nothing to execute; the
    fact is already known.
    """
    return Step(
        id=next_id,
        task="Determine today's actual date to anchor all recency-related reasoning and searches in this plan.",
        tool_hint="none",
        status=StepStatus.DONE,
        result=f"Today's date is {today_date()}.",
    )


def plan_node(state: State) -> dict:
    """Break down the input task into a plan using the breakdown_task function.

    Two deterministic shortcuts, both bypassing the LLM planner's own
    (inconsistent) judgment about when the date matters:

    1. Pure date queries ("what's today's date?", "whats todays date?") skip
       planning and search entirely — a single DONE step with the real date
       and an immediate final_answer is the whole plan. Previously even this
       trivial case triggered a full web search for something the process
       already knows via today_date().

    2. Goals that merely REFERENCE recency ("who won the world cup this
       year") get a date-anchor step prepended before the LLM planner's own
       steps, so every later step/search has the real date available from
       the start — see _extract_search_context, which auto-folds short prior
       results (including this anchor) into later search queries.
    """
    goal = state.get("input", "")

    if _is_pure_date_query(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        plan = Plan(
            goal=goal,
            subtasks=[anchor_step],
            final_answer=anchor_step.result,
        )
        return {"plan": plan}

    plan = breakdown_task(goal)

    if _needs_date_anchor(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        # Renumber the planner's own steps to come after the anchor step.
        for i, step in enumerate(plan.subtasks, start=2):
            step.id = i
        plan.subtasks = [anchor_step] + plan.subtasks

    return {"plan": plan}



def _check_search_relevance(step_task: str, goal: str, result: str) -> tuple[bool, str]:
    """
    Ask the LLM whether a search result actually answers the step it was
    meant to answer, as opposed to merely having executed successfully.

    This closes a gap where a search could return DONE with plausible-looking
    but irrelevant/stale/off-target content (e.g. searching for "the most
    recent World Cup winner" and getting a list of historical winners with no
    signal about whether the current tournament has concluded). Previously
    nothing distinguished that from a genuinely useful result — both looked
    identical to the graph (status=DONE), so a bad result would flow straight
    into synthesis with no chance to replan around it.

    Returns (is_relevant, reason). reason is a short explanation used as the
    step's error message when irrelevant, so the replanner has something
    concrete to react to rather than just "step failed."

    Deliberately a single short, cheap LLM call — not full synthesis-grade
    reasoning — since this runs after every search and shouldn't meaningfully
    add to latency/cost per step.
    """
    # Truncate — this check only needs enough of the result to judge
    # relevance, not the full text (keeps the check itself fast and cheap).
    excerpt = result[:2000]

    check_prompt = f"""Goal: "{goal}"
Step this search was meant to answer: "{step_task}"

Search result excerpt:
{excerpt}

Does this search result contain information that actually answers the step above — not just topically related content, but the specific fact(s) needed?

Respond in EXACTLY this format, nothing else:
RELEVANT: yes or no
REASON: one short sentence explaining why"""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a strict relevance checker. Be skeptical — topically-related content that doesn't contain the specific answer counts as NOT relevant."),
        HumanMessage(content=check_prompt),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    is_relevant = True
    reason = ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("RELEVANT:"):
            is_relevant = "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""

    if not reason:
        reason = "Search result did not contain the specific information needed for this step."

    return is_relevant, reason


def tavily_search_node(state: State) -> dict:
    """
    Execute Tavily search for the current step.
    
    This node is called when a step has tool_hint="web_search" or "tavily_search".
    It performs the search using the tavily_search function and updates the step
    with the result.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("tavily_search_node called with no plan in state")

    # Find the currently running step
    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("tavily_search_node called with no RUNNING step")

    try:
        # Extract search query from the task description, including goal context
        query = f"{plan.goal} — {current_step.task}"

        # Fold in short, targeted context from prior steps (e.g. a year
        # determined by an earlier reason_node step). Previously this
        # function had no visibility into prior results at all, so a
        # correctly-determined fact like "the current year is 2026" never
        # reached the actual search query — search would default to
        # historically dominant results instead of recency-anchored ones.
        search_context = _extract_search_context(plan, current_step)
        if search_context:
            query = f"{query} {search_context}"

        # Determine search depth based on step type
        # Use "basic" for status-check queries, "advanced" for detailed searches
        task_lower = current_step.task.lower()
        status_check_keywords = ["status", "current stage", "has the", "is the", "what is the current", "ongoing", "progress"]
        is_status_check = any(keyword in task_lower for keyword in status_check_keywords)
        
        search_depth = "basic" if is_status_check else "advanced"

        # Bias toward live/news results when either the overall goal or this
        # specific step carries recency language ("latest", "current",
        # "this year", etc.) — reuses the same detection already built for
        # the deterministic date-anchor step, rather than a second regex.
        # This matters because general web search happily surfaces
        # well-indexed historical/reference content (e.g. a "F1 race winners"
        # page that still lists last year's race) even when a plain day-count
        # filter is applied — see tavily_search's recency_sensitive param.
        recency_sensitive = _needs_date_anchor(plan.goal) or _needs_date_anchor(current_step.task)

        result = tavily_search(query, search_depth=search_depth, recency_sensitive=recency_sensitive)

        # A search can succeed (no exception, real content returned) while
        # still being useless for this specific step — e.g. returning a
        # historical winners list when the step needed "has this year's
        # tournament concluded". Without this check that case looked
        # identical to a genuinely useful result (status=DONE), so it flowed
        # straight into synthesis with no opportunity to replan.
        is_relevant, reason = _check_search_relevance(current_step.task, plan.goal, result)
        if is_relevant:
            current_step.status = StepStatus.DONE
            current_step.result = result
        else:
            current_step.status = StepStatus.FAILED
            current_step.error = f"Search returned content, but it doesn't answer this step: {reason}"
            # Keep the raw result too — even an "irrelevant" search can carry
            # useful signal (e.g. a mention of "semi-finals" that hints at
            # what to search for next), and the replanner's context-building
            # step only looks at DONE steps' results, not FAILED ones' raw
            # result field, so this is preserved for debugging/visibility
            # without changing replan behavior.
            current_step.result = result
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)

    return {"plan": plan, "steps_executed": 1}


def reason_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "none" — i.e. a pure-reasoning step with
    no external tool call (e.g. "determine the current date", "plan the
    itinerary", "create a budget", "identify the winner from prior results").

    Previously these steps were routed to `stub_node`, which just marked them
    DONE with a placeholder string and did no actual work. That silently
    dropped steps the planner considered load-bearing — e.g. "determine the
    current year" never running meant downstream searches had no year anchor,
    and "plan the itinerary" never running meant a trip-planning goal's core
    deliverable was just missing from the final answer.

    This node makes a real LLM call, grounded in:
      - the current date (so date/recency-dependent reasoning steps like
        "what year is it" or "has this event happened yet" have a real anchor
        instead of falling back on the model's stale training data)
      - the original goal
      - all prior DONE steps' results, so this step can build on earlier
        research (e.g. "plan the itinerary" can use the weather/accommodation
        results already gathered)
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("reason_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("reason_node called with no RUNNING step")

    try:
        prior_context = []
        for step in plan.subtasks:
            if step.id == current_step.id:
                break
            if step.status == StepStatus.DONE and step.result:
                result_str = step.result
                if len(result_str) > 1500:
                    result_str = result_str[:1500] + "... [truncated]"
                prior_context.append(f"Step {step.id}: {step.task}\nResult: {result_str}")

        context_block = "\n\n".join(prior_context) if prior_context else "(no prior step results)"
        today = date.today().isoformat()

        reasoning_prompt = f"""Today's date is {today}.

Overall goal: "{plan.goal}"

You are performing ONE step of a larger plan toward that goal. This step requires reasoning/synthesis, not an external tool call.

Step to complete: {current_step.task}

Prior step results so far:
{context_block}

Instructions:
- Complete this step directly and concretely, using today's date and the prior results above where relevant.
- If this step depends on information not present in the prior results and not derivable from today's date, say plainly what's missing rather than guessing.
- Do not restate the whole goal — just produce the output this specific step calls for.
- Be concise but complete."""

        llm = get_llm()
        messages = [
            SystemMessage(content="You are a careful reasoning assistant completing one step of a larger plan."),
            HumanMessage(content=reasoning_prompt),
        ]
        response = llm.invoke(messages)

        current_step.status = StepStatus.DONE
        current_step.result = response.content
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)

    return {"plan": plan, "steps_executed": 1}


def executor_node(state: State) -> dict:
    """
    Execute the next PENDING step in the plan.

    Finds the first step with status PENDING, marks it RUNNING, and returns
    the tool_hint for routing to the appropriate tool node.

    Only processes ONE step per call — the graph's conditional edge decides
    which tool node to route to based on tool_hint.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("executor_node called with no plan in state")

    next_step = next((s for s in plan.subtasks if s.status == StepStatus.PENDING), None)
    if next_step is None:
        # Nothing left to do - all steps are either DONE or FAILED
        return {"plan": plan}

    next_step.status = StepStatus.RUNNING

    return {"plan": plan}


def synthesize_node(state: State) -> dict:
    """
    Synthesize all step results into a final answer using the LLM.

    This node is called when all steps are complete and the final step has
    tool_hint="none". It concatenates all step results and asks the LLM to
    provide a comprehensive answer to the original goal.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("synthesize_node called with no plan in state")

    # Collect all step results
    step_results = []
    for step in plan.subtasks:
        if step.result:
            result_str = step.result
            if len(result_str) > 1500:
                result_str = result_str[:1500] + "... [truncated]"
            step_results.append(f"Step {step.id}: {step.task}\nResult: {result_str}")
        elif step.error:
            step_results.append(f"Step {step.id}: {step.task}\nError: {step.error}")

    if not step_results:
        # No results to synthesize
        plan.final_answer = "No step results were available to synthesize a final answer."
        return {"plan": plan}

    # Build synthesis prompt
    synthesis_prompt = f"""You are given raw, noisy scraped web content related to: "{plan.goal}"

The content contains navigation menus, stadium tables, and unrelated trivia mixed in with the actual relevant facts. Your job:

1. Find the specific fact(s) that answer the goal — dates, scores, team names, match stage (group/knockout/semi/final).
2. Ignore boilerplate, image alt-text, navigation links, stadium capacity tables, and unrelated historical trivia.
3. Determine the MOST RECENT dated event relevant to the goal — sort by date, not by position in the text.
4. If the specific event asked about (e.g., "the final") hasn't occurred, identify the most recent completed match instead from the data provided, and answer using that — do not simply state that no winner was found.
5. Give a direct, confident answer grounded only in facts present in the search results. Do not hedge with "consult a live source" — you have the current data, use it.

Search results:
{chr(10).join(step_results)}"""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a helpful synthesis assistant that combines information from multiple sources."),
        HumanMessage(content=synthesis_prompt),
    ]
    response = llm.invoke(messages)

    # Store the synthesis result directly on the plan. This no longer depends
    # on a step having tool_hint="none" existing in the plan — the planner
    # prompt isn't guaranteed to always emit one, and when it doesn't, the
    # synthesized answer was previously silently discarded.
    plan.final_answer = response.content

    return {"plan": plan}

MAX_REPLAN = 4
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
    
    previous_str = "\n".join(previous_context)
    new_str = "\n".join(new_context)
    
    # Truncate to keep the check fast and cheap
    previous_excerpt = previous_str[:3000]
    new_excerpt = new_str[:3000]
    
    novelty_prompt = f"""Previous step results:
{previous_excerpt}

New step results:
{new_excerpt}

Does the new step results contain genuinely new information that wasn't present in the previous results? Consider:
- Are there new facts, dates, or specific details?
- Is there new perspective or analysis?
- Or is this essentially the same information rephrased?

Respond in EXACTLY this format, nothing else:
HAS_NEW_INFO: yes or no
REASON: one short sentence explaining why"""

    llm = get_llm()
    messages = [
        SystemMessage(content="You are a strict novelty checker. Be skeptical — rephrased or marginally different content counts as NOT having new information."),
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


def replaner(state: State) -> dict:
    """
    Replan the remaining steps in the plan.

    This function is called when a step fails (status=FAILED) and it will evaluate
    the output of steps that are finished and will decied to continue or revies. It will
    generate a new plan for the remaining tasks, replacing the old plan
    in the state. The new plan will only include steps that are still
    PENDING or RUNNING, and will re-evaluate how to achieve the goal.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("replaner called with no plan in state")

    # Check for consecutive identical replans - early termination
    consecutive_count = state.get("consecutive_identical_replans", 0)
    if consecutive_count >= MAX_CONSECUTIVE_IDENTICAL_REPLANS:
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
        # Mark all remaining PENDING/RUNNING steps as CANCELLED instead of FAILED
        cancelled_steps = [s for s in plan.subtasks if s.status in (StepStatus.PENDING, StepStatus.RUNNING)]
        for step in cancelled_steps:
            step.status = StepStatus.CANCELLED
            step.error = f"Replan limit ({MAX_REPLAN}) exceeded - execution terminated"
        plan.cancelled_steps.extend(cancelled_steps)
        # Remove cancelled steps from subtasks (filter by original status before we changed it)
        plan.subtasks = [s for s in plan.subtasks if s.status not in (StepStatus.CANCELLED,)]
        return {"plan": plan}

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
    previous_context = state.get("last_replan_context")
    if previous_context is None:
        # No prior replan cycle to compare against yet (this is the first
        # replan in the run) — nothing to judge novelty against.
        has_new_info, novelty_reason = True, "First replan - no previous context to compare"
    else:
        has_new_info, novelty_reason = _check_replan_novelty(previous_context, completed_results)

    # Generate a new plan based on the original goal and the results of completed steps
    new_plan = breakdown_task(plan.goal, context=completed_results)

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

