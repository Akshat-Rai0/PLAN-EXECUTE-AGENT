"""Search, query preprocessing, and reasoning nodes."""

import os
import re
from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.prompts.loader import load_prompt
from ..state import State, StepStatus
from .common import _log_approval, _verify_step_result, _pkg
from .planning import (
    _YEAR_PATTERN,
    _SHORT_RESULT_CHAR_LIMIT,
)

def _search_relevance_validation_enabled() -> bool:
    """Keep the costly second LLM search check opt-in for production runs."""
    return os.getenv("VALIDATE_SEARCH_RELEVANCE", "false").lower() in {"1", "true", "yes"}


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

    check_prompt = load_prompt("plan_execute", "search_relevance").format(**locals())

    llm = _pkg().get_llm()
    messages = [
        SystemMessage(content=load_prompt("plan_execute", "search_relevance_system")),
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

def preprocess_search_query(
    goal: str,
    step_task: str,
    prior_context: str = "",
    current_date: str | None = None,
) -> str:
    """
    Pre-process and rewrite an ambiguous or conversational step task into an
    exact, keyword-dense search query optimized for Tavily search.

    Uses a fast/cheap LLM with a robust heuristic fallback on error or empty response.
    """
    anchor = current_date or _pkg().today_date()
    
    # 1. Try LLM-based query reformulation
    try:
        sys_prompt = load_prompt("plan_execute", "search_query_rewrite_system")
        user_prompt = load_prompt("plan_execute", "search_query_rewrite").format(
            goal=goal,
            step_task=step_task,
            prior_context=prior_context or "None",
            current_date=anchor,
        )
        
        cheap_llm = _pkg().get_cheap_llm()
        response = cheap_llm.invoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        rewritten = response.content.strip() if hasattr(response, "content") else str(response).strip()
        # Strip out any lingering wrapping quotes or "Query:" prefixes
        rewritten = re.sub(r'^(query|search query|rewritten query):\s*', '', rewritten, flags=re.IGNORECASE)
        rewritten = rewritten.strip('"`\'\n ')
        
        if rewritten and len(rewritten) >= 3:
            # Cap at Tavily query length limit
            TAVILY_MAX_QUERY_CHARS = 400
            return rewritten[:TAVILY_MAX_QUERY_CHARS].rstrip()
    except Exception as exc:
        print(f"⚠️ Search query pre-processor LLM failed ({exc}), falling back to heuristic cleanup")

    # 2. Heuristic fallback
    cleaned_task = re.sub(
        r'^(step\s*\d+[\s:.-]*|search\s+(for|google|web|online|tavily)?[\s:.-]*|find\s+(out)?[\s:.-]*|look\s+up[\s:.-]*|check\s+(if)?[\s:.-]*)',
        '',
        step_task.strip(),
        flags=re.IGNORECASE
    ).strip()
    
    if not cleaned_task:
        cleaned_task = step_task.strip()
        
    query = f"{goal} — {cleaned_task}"
    if prior_context:
        query = f"{query} {prior_context}"
        
    TAVILY_MAX_QUERY_CHARS = 400
    if len(query) > TAVILY_MAX_QUERY_CHARS:
        query = f"{cleaned_task} {prior_context}".strip() if prior_context else cleaned_task
        if len(query) > TAVILY_MAX_QUERY_CHARS:
            query = query[:TAVILY_MAX_QUERY_CHARS].rstrip()
            
    return query


def search_query_preprocessor_node(state: State) -> dict:
    """
    Dedicated pre-processing node for Tavily search queries.
    Rewrites the running step's task into an unambiguous search query.
    """
    plan = state.get("plan")
    if plan is None:
        return {"plan": plan}
    
    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        return {"plan": plan}

    prior_context = _extract_search_context(plan, current_step)
    rewritten_query = preprocess_search_query(
        goal=plan.goal,
        step_task=current_step.task,
        prior_context=prior_context,
    )
    print(f"🔍 [Query Preprocessor] Rewrote query to: '{rewritten_query}'")
    return {"plan": plan}


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

    # Log LOW-risk operation
    log_update = _log_approval(state, "tavily_search", current_step.task)

    try:
        # Extract search context from prior steps
        search_context = _extract_search_context(plan, current_step)

        # Pre-process and rewrite the search query to eliminate ambiguity and conversational artifacts
        query = preprocess_search_query(
            goal=plan.goal,
            step_task=current_step.task,
            prior_context=search_context,
        )
        print(f"🔍 Preprocessed search query: '{query}'")

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
        recency_sensitive = _pkg()._needs_date_anchor(plan.goal) or _pkg()._needs_date_anchor(current_step.task)

        result = _pkg().tavily_search(query, search_depth=search_depth, recency_sensitive=recency_sensitive)

        # A search can succeed (no exception, real content returned) while
        # still being useless for this specific step — e.g. returning a
        # historical winners list when the step needed "has this year's
        if not _pkg()._search_relevance_validation_enabled():
            current_step.status = StepStatus.DONE
            current_step.result = result
            print(f"✅ Search completed")
            print(f"👁️  Result: {result[:300]}{'...' if len(result) > 300 else ''}")
        else:
            is_relevant, reason = _pkg()._check_search_relevance(current_step.task, plan.goal, result)
            if is_relevant:
                current_step.status = StepStatus.DONE
                current_step.result = result
                print(f"✅ Search completed (relevance validated)")
            else:
                current_step.status = StepStatus.FAILED
                print(f"❌ Search result deemed irrelevant: {reason}")
                current_step.error = f"Search returned content, but it doesn't answer this step: {reason}"
                current_step.result = result
                
        # Verification Check
        if current_step.status == StepStatus.DONE and current_step.success_criterion:
            is_verified, hint, err_msg = _verify_step_result(current_step)
            if not is_verified:
                current_step.verification_attempts += 1
                if current_step.verification_attempts < 2:
                    current_step.status = StepStatus.PENDING
                    append_hint = f" (Entities from last try: {hint})" if hint else ""
                    current_step.task = current_step.task + append_hint
                    print(f"⚠️ Step verification failed. Retrying with augmented task: {current_step.task}")
                    return {"plan": plan, "steps_executed": 1, "replan_count": 1, **log_update}
                else:
                    current_step.status = StepStatus.DONE
                    current_step.result = f"[UNVERIFIED: could not confirm '{current_step.success_criterion}' after 2 attempts] " + (current_step.result or "")
                    print(f"⚠️ Step verification failed after 2 attempts. Marking DONE with UNVERIFIED prefix.")

    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)
        print(f"❌ Search error: {str(e)}")

    return {"plan": plan, "steps_executed": 1, **log_update}


def reason_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "none" — i.e. a pure-reasoning step with
    no external tool call (e.g. "determine the current date", "plan the
    itinerary", "create a budget", "identify the winner from prior results").

    WHEN TO USE:
    - For analysis, planning, or synthesis of existing information
    - When you have all necessary context and just need to process it
    - For decision-making based on prior step results
    - For summarizing or combining information from multiple sources
    - When the task requires logical reasoning but no external data
    - For planning itineraries, budgets, or strategies based on gathered info

    WHEN NOT TO USE:
    - When you need to gather new information (use tavily_search instead)
    - For calculations or data processing (use code_executor instead)
    - When you need to interact with files or systems (use appropriate tools)
    - When the task requires external APIs or services
    - For tasks that need visual understanding (use browser_use)

    EXAMPLES:
    - "Analyze the search results and identify the best option"
    - "Plan a 3-day itinerary based on the gathered information"
    - "Create a budget from the price information collected"
    - "Determine the winner from the tournament results"
    - "Summarize the key findings from the research"
    - "Compare the options and recommend the best choice"

    CAPABILITIES:
    - Grounded in current date (recency-aware reasoning)
    - Access to all prior step results for context
    - Can synthesize information from multiple sources
    - Makes real LLM calls (not silent no-ops)
    - LOW-risk classification (no external side effects)

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

    # Log LOW-risk operation
    log_update = _log_approval(state, "reason", current_step.task)

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

        reasoning_prompt = load_prompt("plan_execute", "reason").format(**locals())

        llm = _pkg().get_llm()
        messages = [
            SystemMessage(content=load_prompt("plan_execute", "reason_system")),
            HumanMessage(content=reasoning_prompt),
        ]
        response = llm.invoke(messages)

        current_step.status = StepStatus.DONE
        current_step.result = response.content
        print(f"✅ Reasoning completed")
        print(f"👁️  Result: {response.content[:300]}{'...' if len(response.content) > 300 else ''}")
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)
        print(f"❌ Reasoning failed: {str(e)}")

    return {"plan": plan, "steps_executed": 1, **log_update}
