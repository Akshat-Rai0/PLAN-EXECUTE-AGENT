import re
from .state import Turn, ReactState
from src.tools.registry import tavily_search, today_date
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.plan_execute.llm import get_llm


def _render_history(history: list[Turn]) -> str:
    """Render completed turns (where observation is not None) for the prompt."""
    rendered = []
    for turn in history:
        if turn.observation is not None:
            rendered.append(
                f"Thought: {turn.thought}\n"
                f"Action: {turn.action}\n"
                f"Action Input: {turn.action_input}\n"
                f"Observation: {turn.observation}\n\n"
            )
    return "".join(rendered)


def _parse_react_response(content: str) -> tuple[str, str, str]:
    """Parse LLM response to extract Thought, Action, and Action Input.
    
    Returns tuple of (thought, action, action_input).
    If parsing fails, returns ("", "", "") to indicate a failed turn.
    """
    # Try to match the pattern with colons
    pattern = r"Thought:\s*(.*?)\s*Action:\s*(.*?)\s*Action Input:\s*(.*)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    
    if match:
        thought = match.group(1).strip()
        action = match.group(2).strip()
        action_input = match.group(3).strip()
        return (thought, action, action_input)
    
    # If pattern doesn't match, return empty strings to indicate failure
    return ("", "", "")


def react_step(state: ReactState) -> dict:
    goal = state["goal"]
    history = state.get("history", [])

    # Build the prompt: goal + full history rendered as Thought/Action/Observation text
    history_text = _render_history(history)  # "Thought: ...\nAction: ...\nObservation: ...\n\n" repeated
    
    # Build messages for LLM
    system_message = SystemMessage(
        content="You are a helpful assistant that responds in the exact format: "
        "Thought: ... Action: ... Action Input: ..."
    )
    
    human_message = HumanMessage(
        content=f"""Goal: {goal}

{history_text}

Available actions: web_search(query), today_date(), final_answer(answer)

What is your next Thought and Action? Respond in this exact format:
Thought: <your reasoning>
Action: <tool name>
Action Input: <input to the tool, or the final answer text if Action is final_answer>"""
    )

    response = get_llm().invoke([system_message, human_message])
    thought, action, action_input = _parse_react_response(response.content)

    if action == "final_answer":
        return {"final_answer": action_input, "iterations": 1}

    # If parsing failed, create a failed turn
    if not thought or not action:
        turn = Turn(
            thought=response.content[:200] if response.content else "No thought generated",
            action="error",
            action_input="",
            observation="Parse error: Could not extract Thought, Action, and Action Input from LLM response"
        )
        return {"history": [turn], "iterations": 1}

    # Execute the chosen tool — REUSE existing tools, don't reimplement
    if action == "web_search":
        observation = tavily_search(action_input)
    elif action == "today_date":
        observation = today_date()
    else:
        observation = f"Unknown action: {action}"

    turn = Turn(thought=thought, action=action, action_input=action_input, observation=observation)
    return {"history": [turn], "iterations": 1}