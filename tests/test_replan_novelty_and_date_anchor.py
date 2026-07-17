"""
Regression tests for two fixes:

1. The replan-novelty check bug: previously it compared "results so far"
   against a freshly-generated, not-yet-executed new plan (always empty),
   so it always concluded "no new info" and terminated after one real
   replan cycle. Fixed by tracking `last_replan_context` in state and
   comparing real execution outcomes against real execution outcomes,
   one cycle later.

2. Deterministic date-anchor injection: goals containing recency language
   ("latest", "recent", "this year", etc.) get a guaranteed first step
   that calls today_date() directly, rather than relying on the LLM
   planner to remember to add a "determine current date" step.
"""

import pytest
from src.agents.plan_execute.nodes import (
    replaner,
    plan_node,
    _needs_date_anchor,
    MAX_CONSECUTIVE_IDENTICAL_REPLANS,
)
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


# --- Novelty check fix -------------------------------------------------

def test_first_replan_never_counts_as_identical():
    """
    With no last_replan_context in state (first replan of the run),
    consecutive_identical_replans should reset to 0, not increment —
    there's nothing to compare against yet.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="timeout"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0,
        "consecutive_identical_replans": 0,
        # No last_replan_context key at all — first replan in the run
    }

    new_plan = Plan(
        goal="test goal",
        subtasks=[Step(id=1, task="revised step", tool_hint="web_search", status=StepStatus.PENDING)]
    )

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = new_plan

        result = replaner(state)

        assert result["consecutive_identical_replans"] == 0
        # last_replan_context should now be populated with this cycle's
        # completed_results, ready for the NEXT replan to compare against
        assert result["last_replan_context"] is not None


def test_novelty_check_compares_against_stored_prior_context_not_new_plan():
    """
    Direct regression test for the core bug: the novelty check must compare
    against state["last_replan_context"] (real prior execution results),
    NOT against the freshly-generated new_plan's subtasks (which are always
    empty/PENDING and never contain results).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Genuinely new fact: X happened"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 1,
        "consecutive_identical_replans": 0,
        # Simulate a prior replan cycle that had DIFFERENT results
        "last_replan_context": ["Step 1: old step\nResult: completely different old fact"],
    }

    new_plan = Plan(
        goal="test goal",
        subtasks=[Step(id=1, task="next step", tool_hint="web_search", status=StepStatus.PENDING)]
    )

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = new_plan

        with patch('src.agents.plan_execute.nodes._check_replan_novelty') as mock_novelty:
            mock_novelty.return_value = (True, "Genuinely new info found")

            replaner(state)

            # Verify _check_replan_novelty was called with the STORED prior
            # context (from state) and the CURRENT completed_results — not
            # with the new_plan's (always-empty) subtasks.
            call_args = mock_novelty.call_args
            previous_arg, new_arg = call_args[0]

            assert previous_arg == state["last_replan_context"], \
                "Novelty check should compare against stored last_replan_context"
            assert any("Genuinely new fact: X happened" in item for item in new_arg), \
                "Novelty check should compare against THIS cycle's actual completed_results"


def test_consecutive_count_resets_on_new_info():
    """
    Regression test for the reducer bug: returning consecutive_identical_replans=0
    must actually reset the value (replace semantics), not add 0 to an
    accumulating total (which would leave a high count unchanged).
    """
    from src.agents.plan_execute.state import replace_consecutive_identical_replans

    # Simulate an existing high count, then a reset
    result = replace_consecutive_identical_replans(existing=5, new=0)
    assert result == 0, "Reducer must replace, not sum — resetting to 0 must actually reset"


def test_consecutive_count_increments_correctly():
    """
    When no new info is found, consecutive_identical_replans should increment
    by exactly 1 from its current value, not jump to a hardcoded 1.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Same old fact"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 2,
        "consecutive_identical_replans": 1,  # already at 1 from a prior cycle
        "last_replan_context": ["Step 1: old\nResult: Same old fact"],
    }

    new_plan = Plan(
        goal="test goal",
        subtasks=[Step(id=1, task="next step", tool_hint="web_search", status=StepStatus.PENDING)]
    )

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = new_plan

        with patch('src.agents.plan_execute.nodes._check_replan_novelty') as mock_novelty:
            mock_novelty.return_value = (False, "Same information as before")

            result = replaner(state)

            assert result["consecutive_identical_replans"] == 2, \
                "Should increment from 1 to 2, not reset to 1"


def test_consecutive_identical_replans_triggers_termination():
    """
    When consecutive_identical_replans hits MAX_CONSECUTIVE_IDENTICAL_REPLANS,
    replaner should terminate immediately (CANCELLED steps, no breakdown_task
    call) rather than burning through the rest of MAX_REPLAN.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 1,  # well under MAX_REPLAN
        "consecutive_identical_replans": MAX_CONSECUTIVE_IDENTICAL_REPLANS,
    }

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        result = replaner(state)

        mock_breakdown.assert_not_called()
        assert len(result["plan"].cancelled_steps) == 1
        assert result["plan"].cancelled_steps[0].status == StepStatus.CANCELLED


# --- Pure date query fast-path & "todays" regex fix ----------------------

@pytest.mark.parametrize("goal", [
    "whats todays date ?",
    "what's today's date",
    "today's date",
    "what is the current date",
    "what is today's day",
])
def test_needs_date_anchor_catches_todays_without_apostrophe(goal):
    """
    Regression test for the exact bug: "whats todays date ?" (no apostrophe
    in "todays") previously did NOT match \\btoday\\b, since there's no word
    boundary between "y" and "s" — both are word characters. This slipped
    through undetected and triggered a full unnecessary web search.
    """
    from src.agents.plan_execute.nodes import _needs_date_anchor
    assert _needs_date_anchor(goal) is True, f"Should detect date reference in: {goal!r}"


@pytest.mark.parametrize("goal", [
    "whats todays date ?",
    "what's today's date",
    "today's date",
    "what is the current date",
    "tell me today's date",
])
def test_is_pure_date_query_detects_date_only_goals(goal):
    from src.agents.plan_execute.nodes import _is_pure_date_query
    assert _is_pure_date_query(goal) is True, f"Should be a pure date query: {goal!r}"


@pytest.mark.parametrize("goal", [
    "who won the world cup this year",
    "what's the latest news on AI",
    "explain photosynthesis",
])
def test_is_pure_date_query_ignores_non_pure_goals(goal):
    """
    Goals that reference recency/date as part of a larger question should NOT
    be treated as pure date queries — they still need the full plan, just
    with a date anchor prepended (see _needs_date_anchor).
    """
    from src.agents.plan_execute.nodes import _is_pure_date_query
    assert _is_pure_date_query(goal) is False, f"Should NOT be a pure date query: {goal!r}"


def test_plan_node_pure_date_query_skips_planning_and_search():
    """
    For a pure date query, plan_node should skip breakdown_task entirely
    (no LLM planning call, no search) and return a single DONE step plus a
    final_answer already set — the whole goal is answered by today_date().
    """
    state: State = {"input": "whats todays date ?", "plan": None}

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        with patch('src.agents.plan_execute.nodes.today_date') as mock_today:
            mock_today.return_value = "2026-07-16"

            result = plan_node(state)

            mock_breakdown.assert_not_called()

            plan = result["plan"]
            assert len(plan.subtasks) == 1
            assert plan.subtasks[0].status == StepStatus.DONE
            assert "2026-07-16" in plan.subtasks[0].result
            assert plan.final_answer is not None
            assert "2026-07-16" in plan.final_answer


@pytest.mark.parametrize("goal", [
    "who won the world cup this year",
    "what's the latest news on AI",
    "give me the most recent match results",
    "what is happening currently in the market",
    "show me today's headlines",
    "what's the current status of the project",
    "any updates so far",
])
def test_needs_date_anchor_detects_recency_language(goal):
    assert _needs_date_anchor(goal) is True, f"Should detect recency language in: {goal!r}"


@pytest.mark.parametrize("goal", [
    "who won the 2022 world cup",
    "explain how photosynthesis works",
    "write a hello world program in python",
    "what is the capital of France",
])
def test_needs_date_anchor_ignores_non_recency_goals(goal):
    assert _needs_date_anchor(goal) is False, f"Should NOT flag non-recency goal: {goal!r}"


def test_plan_node_prepends_date_anchor_for_recency_goal():
    """
    For a goal with recency language, plan_node should prepend a real
    date-anchor step (id=1, DONE, using today_date()) before the LLM
    planner's own steps, and renumber those steps to follow it.
    """
    mock_plan = Plan(
        goal="who won the world cup this year",
        subtasks=[
            Step(id=1, task="search for the world cup", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="determine the winner", tool_hint="none", status=StepStatus.PENDING),
        ]
    )
    state: State = {"input": "who won the world cup this year", "plan": None}

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_plan

        with patch('src.agents.plan_execute.nodes.today_date') as mock_today:
            mock_today.return_value = "2026-07-16"

            result = plan_node(state)

            subtasks = result["plan"].subtasks
            assert len(subtasks) == 3, "Date anchor step should be prepended, total steps = 2 + 1"

            anchor = subtasks[0]
            assert anchor.id == 1
            assert anchor.status == StepStatus.DONE
            assert anchor.tool_hint == "none"
            assert "2026-07-16" in anchor.result

            # Original planner steps should be renumbered to follow the anchor
            assert subtasks[1].id == 2
            assert subtasks[1].task == "search for the world cup"
            assert subtasks[2].id == 3
            assert subtasks[2].task == "determine the winner"


def test_plan_node_no_anchor_for_non_recency_goal():
    """
    For a goal with no recency language, plan_node should NOT prepend a
    date-anchor step — the planner's original steps should be untouched.
    """
    mock_plan = Plan(
        goal="explain photosynthesis",
        subtasks=[
            Step(id=1, task="explain the process", tool_hint="none", status=StepStatus.PENDING),
        ]
    )
    state: State = {"input": "explain photosynthesis", "plan": None}

    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_plan

        result = plan_node(state)

        subtasks = result["plan"].subtasks
        assert len(subtasks) == 1
        assert subtasks[0].id == 1
        assert subtasks[0].task == "explain the process"


def test_date_anchor_step_is_short_enough_to_be_folded_into_search_context():
    """
    Sanity check that the date-anchor step's result stays under
    _SHORT_RESULT_CHAR_LIMIT, so _extract_search_context automatically
    folds it into the next search step's query with no extra wiring.
    """
    from src.agents.plan_execute.nodes import _make_date_anchor_step, _SHORT_RESULT_CHAR_LIMIT

    with patch('src.agents.plan_execute.nodes.today_date') as mock_today:
        mock_today.return_value = "2026-07-16"
        step = _make_date_anchor_step(next_id=1)

        assert len(step.result) <= _SHORT_RESULT_CHAR_LIMIT
