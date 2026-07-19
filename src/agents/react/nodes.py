import re
from .state import Turn, ReactState
from src.tools.registry import (
    tavily_search,
    today_date,
    shell_command_tool,
    write_file_tool,
    start_dev_server_tool,
)
from src.sandbox.shell_runner import make_project_workspace
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.plan_execute.llm import get_llm

MAX_HISTORY_TURNS_IN_PROMPT = 6
MAX_HISTORY_CHARS_IN_PROMPT = 9_000
MAX_TURN_FIELD_CHARS = 1_500


def _truncate(value: str, limit: int = MAX_TURN_FIELD_CHARS) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit - 80]}\n... [truncated] ...\n{value[-60:]}"


def _render_history(history: list[Turn]) -> str:
    """Render a bounded recent history, avoiding quadratic prompt growth."""
    completed = [turn for turn in history if turn.observation is not None]
    recent = completed[-MAX_HISTORY_TURNS_IN_PROMPT:]
    rendered_reversed = []
    used = 0
    # Add newest turns first so a size cap never drops the current context in
    # favour of older observations.
    for turn in reversed(recent):
        rendered = (
            f"Thought: {_truncate(turn.thought)}\n"
            f"Action: {turn.action}\n"
            f"Action Input: {_truncate(turn.action_input)}\n"
            f"Observation: {_truncate(turn.observation)}\n\n"
        )
        if used + len(rendered) > MAX_HISTORY_CHARS_IN_PROMPT:
            break
        rendered_reversed.append(rendered)
        used += len(rendered)
    history_text = "".join(reversed(rendered_reversed))
    omitted = len(completed) - len(rendered_reversed)
    prefix = f"[Earlier {omitted} turns omitted from prompt]\n\n" if omitted else ""
    return prefix + history_text


_TRAILING_PARAGRAPH = re.compile(r"\n\s*\n.*\Z", re.DOTALL)


def _trim_trailing_rambling(text: str) -> str:
    """Cut off any paragraph(s) after the first blank line.

    A clean action_input is expected to be a single value (a query, a
    JSON blob, a command, an answer) — not followed by the model
    continuing to reason after it has already stated its decision.
    """
    return _TRAILING_PARAGRAPH.sub("", text).strip()


_VALID_ACTIONS = frozenset({
    "final_answer",
    "web_search",
    "today_date",
    "set_workspace_path",
    "shell_command",
    "write_file",
    "start_dev_server",
})


def _parse_react_response(content: str) -> tuple[str, str, str]:
    """Parse LLM response to extract Thought, Action, and Action Input.

    Returns tuple of (thought, action, action_input).
    If parsing fails, returns ("", "", "") to indicate a failed turn.

    Only the FIRST Thought/Action/Action Input triple is extracted. Models
    occasionally emit a second "Thought: ... Action: ... Action Input: ..."
    block in the same completion (e.g. narrating a planned follow-up action).
    Without a stop condition, the original greedy `(.*)` with DOTALL would
    swallow that entire second block into action_input, silently corrupting
    the input passed to the tool and the persisted trace.

    Models also sometimes wrap a *valid* block in unstructured rambling —
    reasoning out loud before and/or after the real Thought/Action/Action
    Input triple, occasionally even emitting a literal "Action: ..." as a
    placeholder mid-thought rather than a real action name. That rambling
    isn't a second clean block (the (?=\\n\\s*Thought:) stop condition above
    doesn't fire), so it leaks into `action`/`action_input` verbatim,
    producing bogus "Unknown action" turns or shipping stray prose straight
    into a user-facing final_answer. To catch this: if the captured action
    isn't one of the real action names, re-scan for the LAST occurrence of
    a genuinely valid "Action: <name>" line in the content and re-anchor
    the parse there instead of trusting the first (possibly bogus) match.
    Trailing rambling paragraphs after the real action_input (separated by
    a blank line) are also trimmed, since nothing downstream of a valid
    action should still be "thinking out loud" once the decision is made.
    """
    pattern = r"Thought:\s*(.*?)\s*Action:\s*(.*?)\s*Action Input:\s*(.*?)(?=\n\s*Thought:|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

    if not match:
        return ("", "", "")

    thought = match.group(1).strip()
    action = match.group(2).strip()
    action_input = match.group(3).strip()

    if action.lower() in _VALID_ACTIONS:
        return (thought, action, _trim_trailing_rambling(action_input))

    # First match wasn't a real action (rambling leaked into the Action
    # capture). Look for the last valid "Action: <name>" line in the
    # content instead — the model's actual, final decision tends to be
    # the last clean one it states, with rambling before and after it.
    valid_action_pattern = (
        r"Action:\s*(" + "|".join(re.escape(a) for a in _VALID_ACTIONS) + r")\s*"
        r"Action Input:\s*(.*?)(?=\n\s*Thought:|\n\s*Action:|\Z)"
    )
    valid_matches = list(re.finditer(valid_action_pattern, content, re.DOTALL | re.IGNORECASE))
    if valid_matches:
        last = valid_matches[-1]
        return (thought, last.group(1).strip(), _trim_trailing_rambling(last.group(2).strip()))

    # No recoverable valid action anywhere in the response.
    return ("", "", "")


def react_step(state: ReactState) -> dict:
    goal = state["goal"]
    history = state.get("history", [])
    iteration = len(history) + 1

    print(f"\n{'='*80}")
    print(f"🔄 Step {iteration}")
    print(f"{'='*80}")

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

Available actions:
- web_search(query): Search the web for information using Tavily. Provide a search query string (plain text).
- today_date(): Get today's date in YYYY-MM-DD format. No input needed.
- set_workspace_path(): Create a workspace directory for file operations. No input needed. Must be called before shell_command, write_file, or start_dev_server.
- shell_command(command): Run a shell command in the workspace. Provide the command as a PLAIN STRING. IMPORTANT: If your command has arguments (like "python hello_world.py" or "npm install"), you MUST use "bash -c 'your command'" format. Only base commands like 'python', 'npm', 'ls' are allowed directly. Requires workspace_path to be set via set_workspace_path.
- write_file(path, content): Write a file to the workspace. Action Input must be JSON: {{"path": "relative/path/to/file", "content": "file content"}}. Requires workspace_path to be set via set_workspace_path.
- start_dev_server(command, port): Start a development server. Action Input must be JSON: {{"command": "npm run dev", "port": 5173}}. Requires workspace_path to be set via set_workspace_path.
- final_answer(answer): Provide the final answer to complete the task.

Important patterns:
- To run Python code: First use write_file to create a .py file, then use shell_command "bash -c 'python3 filename.py'" (note: use python3, not python)
- To run commands with arguments: Always use "bash -c 'your command'" format

What is your next Thought and Action? Respond in this exact format:
Thought: <your reasoning>
Action: <tool name>
Action Input: <input to the tool, or the final answer text if Action is final_answer>"""
    )

    response = get_llm().invoke([system_message, human_message])
    thought, action, action_input = _parse_react_response(response.content)

    print(f"💭 Thought: {thought}")
    print(f"🎯 Action: {action}")
    print(f"📝 Action Input: {action_input[:200]}{'...' if len(action_input) > 200 else ''}")

    if action == "final_answer":
        print(f"✅ Final Answer: {action_input}")
        return {"final_answer": action_input, "iterations": 1}

    # If parsing failed, create a failed turn
    if not thought or not action:
        print(f"❌ Parse Error: Could not extract Thought, Action, and Action Input from LLM response")
        turn = Turn(
            thought=response.content[:200] if response.content else "No thought generated",
            action="error",
            action_input="",
            observation="Parse error: Could not extract Thought, Action, and Action Input from LLM response"
        )
        return {"history": [turn], "iterations": 1}

    # Execute the chosen tool — REUSE existing tools, don't reimplement
    workspace_path = state.get("workspace_path")
    
    if action == "web_search":
        observation = tavily_search(action_input)
    elif action == "today_date":
        observation = today_date()
    elif action == "set_workspace_path":
        # Create a workspace directory using the goal as a slug
        import re
        slug = "-".join(goal.lower().split()[:4])
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)[:40]
        workspace_path = make_project_workspace(slug)
        observation = f"Workspace created at: {workspace_path}"
        # Return workspace_path in state update
        turn = Turn(thought=thought, action=action, action_input=action_input, observation=observation)
        return {"history": [turn], "iterations": 1, "workspace_path": workspace_path}
    elif action == "shell_command":
        if not workspace_path:
            observation = "ERROR: workspace_path not set. Cannot run shell commands without a workspace. Use set_workspace_path first."
        else:
            # Handle case where LLM mistakenly sends JSON instead of plain string
            command = action_input
            if action_input.startswith("{"):
                try:
                    import json
                    cmd_data = json.loads(action_input)
                    command = cmd_data.get("command", action_input)
                except json.JSONDecodeError:
                    command = action_input
            observation = shell_command_tool(command, workspace_path)
    elif action == "write_file":
        if not workspace_path:
            observation = "ERROR: workspace_path not set. Cannot write files without a workspace. Use set_workspace_path first."
        else:
            # Parse action_input as JSON: {"path": "relative/path", "content": "file content"}
            try:
                import json
                file_data = json.loads(action_input)
                rel_path = file_data.get("path", "")
                content = file_data.get("content", "")
                if not rel_path:
                    observation = "ERROR: write_file requires 'path' field in action_input JSON"
                else:
                    observation = write_file_tool(rel_path, content, workspace_path)
            except json.JSONDecodeError:
                observation = f"ERROR: write_file action_input must be valid JSON with 'path' and 'content' fields. Got: {action_input}"
    elif action == "start_dev_server":
        if not workspace_path:
            observation = "ERROR: workspace_path not set. Cannot start dev server without a workspace. Use set_workspace_path first."
        else:
            # Parse action_input as JSON: {"command": "npm run dev", "port": 5173}
            try:
                import json
                server_data = json.loads(action_input)
                command = server_data.get("command", "npm run dev")
                port = int(server_data.get("port", 5173))
                observation = start_dev_server_tool(command, workspace_path, port)
            except json.JSONDecodeError:
                observation = f"ERROR: start_dev_server action_input must be valid JSON with 'command' and 'port' fields. Got: {action_input}"
            except ValueError:
                observation = f"ERROR: port must be a number. Got: {server_data.get('port')}"
    else:
        observation = f"Unknown action: {action}"

    print(f"👁️  Observation: {observation[:300]}{'...' if len(observation) > 300 else ''}")

    turn = Turn(thought=thought, action=action, action_input=action_input, observation=observation)
    return {"history": [turn], "iterations": 1}
