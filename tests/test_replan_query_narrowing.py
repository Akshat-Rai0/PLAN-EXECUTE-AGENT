"""
Regression tests for breakdown_task's replan prompt construction.

Context: two separate head-to-head comparisons against a ReAct baseline (F1
"last race" and FIFA World Cup 2026 "latest match") showed the SAME failure
shape: after a search step failed the relevance check because it was too
generic/broad, the replanner's follow-up plan was not meaningfully more
specific, execution eventually got CANCELLED, and synthesis fell back to
stale data from an earlier, unrelated successful step — producing a
confidently wrong final answer.

ReAct, by contrast, organically narrowed its query turn-by-turn ("the winner
is not explicitly stated... I will search for the winner of the 2026 British
Grand Prix specifically") and got the right answer both times, at a
comparable or lower LLM call count.

The fix: breakdown_task's replan prompt now explicitly instructs the LLM to
read failure reasons and write MORE SPECIFIC follow-up steps (using concrete
details already surfaced elsewhere) rather than repeating a similarly broad
query in different words.
"""

import pytest
from src.agents.plan_execute.tools import breakdown_task, PROMPT_TEMPLATE, REPLAN_INSTRUCTIONS
from src.agents.plan_execute.state import Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def _mock_llm_response(json_str: str):
    mock_response = MagicMock()
    mock_response.content = json_str
    return mock_response


def test_replan_prompt_includes_narrowing_instruction():
    """
    When context is provided (i.e. this is a replan, not an initial plan),
    the prompt sent to the LLM must include explicit query-narrowing
    guidance — not just the generic "revise the plan" instruction that
    previously let the LLM regenerate an equally broad follow-up query.
    """
    valid_plan_json = '''{
        "goal": "test goal",
        "subtasks": [
            {"id": 1, "task": "more specific step", "tool_hint": "web_search", "status": "PENDING", "sensitive": false}
        ]
    }'''

    with patch('src.agents.plan_execute.tools.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(valid_plan_json)
        mock_get_llm.return_value = mock_llm

        breakdown_task(
            "test goal",
            context=["Step 1: search for recent matches\nError: Search returned content, but it doesn't answer this step: no explicit winner specified"]
        )

        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        prompt_content = messages[1].content

        assert "MORE SPECIFIC" in prompt_content, \
            "Replan prompt should explicitly instruct narrowing the query"
        assert "doesn't answer" in prompt_content or "doesn't specify" in prompt_content, \
            "Replan prompt should call out the relevance-failure language pattern to watch for"


def test_initial_plan_prompt_does_not_include_replan_instructions():
    """
    An initial plan (no context) should NOT include replan-specific
    narrowing instructions — those only make sense once there's prior
    context to narrow against.
    """
    valid_plan_json = '''{
        "goal": "test goal",
        "subtasks": [
            {"id": 1, "task": "first step", "tool_hint": "web_search", "status": "PENDING", "sensitive": false}
        ]
    }'''

    with patch('src.agents.plan_execute.tools.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(valid_plan_json)
        mock_get_llm.return_value = mock_llm

        breakdown_task("test goal", context=None)

        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        prompt_content = messages[1].content

        assert "MORE SPECIFIC" not in prompt_content
        assert "CRITICAL" not in prompt_content


def test_replan_prompt_includes_actual_context_content():
    """
    Sanity check that the actual failure context text (not just the
    instruction wrapper) makes it into the prompt — the narrowing
    instruction is only useful if the LLM can see what failed and why.
    """
    valid_plan_json = '''{
        "goal": "test goal",
        "subtasks": [
            {"id": 1, "task": "narrower step", "tool_hint": "web_search", "status": "PENDING", "sensitive": false}
        ]
    }'''

    with patch('src.agents.plan_execute.tools.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(valid_plan_json)
        mock_get_llm.return_value = mock_llm

        breakdown_task(
            "test goal",
            context=["Step 2: search for France vs Spain result\nResult: schedule listing, no score given"]
        )

        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        prompt_content = messages[1].content

        assert "France vs Spain" in prompt_content, \
            "Actual prior step context must be present in the prompt, not just the instruction wrapper"


def test_replan_narrowing_instruction_survives_retry():
    """
    If the LLM's first replan response is unparseable, the retry prompt
    should still include the narrowing instruction — not fall back to a
    bare error-correction prompt that drops the guidance.
    """
    valid_plan_json = '''{
        "goal": "test goal",
        "subtasks": [
            {"id": 1, "task": "narrower step", "tool_hint": "web_search", "status": "PENDING", "sensitive": false}
        ]
    }'''

    with patch('src.agents.plan_execute.tools.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        # First call: invalid JSON. Second call: valid.
        mock_llm.invoke.side_effect = [
            _mock_llm_response("not valid json at all"),
            _mock_llm_response(valid_plan_json),
        ]
        mock_get_llm.return_value = mock_llm

        breakdown_task(
            "test goal",
            context=["Step 1: search step\nError: doesn't specify the winner"]
        )

        # Check the SECOND call (the retry) still has the narrowing instruction
        second_call_messages = mock_llm.invoke.call_args_list[1][0][0]
        retry_prompt_content = second_call_messages[1].content

        assert "MORE SPECIFIC" in retry_prompt_content, \
            "Narrowing instruction must survive into the retry prompt after a parse failure"


def test_replan_prompt_handles_blocked_shell_commands():
    """
    A failed shell_command should be rewritten instead of replayed verbatim.
    The replanner prompt should explicitly tell the model to change the command
    shape or switch tools when the command was blocked by the allowlist.
    """
    valid_plan_json = '''{
        "goal": "test goal",
        "subtasks": [
            {"id": 1, "task": "use delete_file instead of rm", "tool_hint": "delete_file", "status": "PENDING", "sensitive": false}
        ]
    }'''

    with patch('src.agents.plan_execute.tools.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _mock_llm_response(valid_plan_json)
        mock_get_llm.return_value = mock_llm

        breakdown_task(
            "test goal",
            context=["Step 1: delete file\nError: Command 'rm' is not in the allowed command list. Allowed: ['bash', 'cat', 'cp']"]
        )

        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        prompt_content = messages[1].content

        assert "allowed command list" in prompt_content
        assert "delete_file" in prompt_content or "Do NOT repeat the same command shape" in prompt_content
