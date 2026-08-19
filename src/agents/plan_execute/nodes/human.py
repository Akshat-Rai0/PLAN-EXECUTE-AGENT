"""Human-in-the-loop approval and question nodes."""

import json
from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from src.tools.risk_classifier import classify_tool_risk, RiskLevel
from src.synthesis.registry import default_registry
from src.agents.prompts.loader import load_prompt
from .common import _pkg
from ..state import State, StepStatus
from .common import _build_coding_context

def extract_user_info_node(state: State) -> dict:
    """
    Extract and store user information from human responses.
    
    This node uses an LLM to identify personal information (name, email, phone, etc.)
    from human responses and stores it in the global UserInfoStore for future form filling.
    """
    from src.tools.user_info_store import get_user_info_store, save_user_info_store
    
    # Get the most recent human response if available
    human_questions = state.get("human_questions", [])
    if not human_questions:
        return {"plan": state["plan"]}
    
    # Get the last human response
    last_response = human_questions[-1].get("response", "")
    if not last_response or isinstance(last_response, dict):
        return {"plan": state["plan"]}
    
    # Use LLM to extract personal information
    llm = _pkg().get_llm()
    extraction_prompt = (
        f"Extract personal information from the following text. Return ONLY valid JSON "
        f"with these fields if present: full_name, email, phone, address, company, job_title. "
        f"Only include fields that are clearly present in the text. "
        f"Text: {last_response}"
    )
    
    try:
        response = llm.invoke(extraction_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON response
        import json
        extracted_info = json.loads(response_text)
        
        # Store extracted information
        store = get_user_info_store()
        for key, value in extracted_info.items():
            if value:  # Only store non-empty values
                store.set_info(key, value, source="conversation", confidence=0.9)
        
        save_user_info_store()
        
        print(f"📝 Extracted and stored user info: {list(extracted_info.keys())}")
        
    except (json.JSONDecodeError, KeyError, ValueError, AttributeError) as e:
        # Extraction failed, but don't block execution
        print(f"⚠️ Failed to extract user info: {e}")
    
    return {"plan": state["plan"]}


def ask_human_node(state: State) -> dict:
    """
    Handle LLM requests to ask the human a question.
    
    This node is called when the LLM wants to ask a human for clarification
    or input. It triggers an interrupt to pause execution and wait for human input.
    On resume, it returns the human's response to the LLM.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("ask_human_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("ask_human_node called with no RUNNING step")

    # Check if the step's result contains an ASK_HUMAN marker
    if current_step.result and current_step.result.startswith("[ASK_HUMAN:"):
        # Extract the question from the result
        question = current_step.result.replace("[ASK_HUMAN: ", "").rstrip("]")
        
        # Trigger interrupt to get human response
        question_payload = {
            "type": "human_question",
            "question": question,
            "step_id": current_step.id,
            "task": current_step.task,
        }
        
        human_response = interrupt(question_payload)

        # Extract human_response from dict if present, otherwise use as-is
        if isinstance(human_response, dict):
            response_text = human_response.get("human_response", str(human_response))
        else:
            response_text = str(human_response)

        # Log the question and response
        question_event = {
            "step_id": current_step.id,
            "question": question,
            "response": human_response,  # Keep original response for debugging
            "response_text": response_text,  # Actual text used
            "timestamp": date.today().isoformat(),
        }

        print(f"❓ Human question: {question}")
        print(f"💬 Human response: {response_text} (raw: {human_response})")

        # Return the human's response as the step result
        current_step.result = response_text
        current_step.status = StepStatus.DONE
        
        return {
            "plan": plan,
            "human_questions": [question_event],
        }
    else:
        # No question to ask, just proceed
        return {"plan": plan}


def approval_node(state: State) -> dict:
    """
    Handle human-in-the-loop approval for HIGH-risk operations.

    This node checks if a pending_approval exists in state. If so, it triggers
    an interrupt to pause execution and wait for human input. On resume, it
    processes the human's decision (approve/reject/alternative) and updates
    the step status accordingly.

    For HIGH-risk tools (shell_command, write_file, code_executor, start_server),
    this node is called before the actual tool execution to ensure human oversight.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("approval_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("approval_node called with no RUNNING step")

    # Check if this step requires approval (HIGH-risk tool)
    risk_level = classify_tool_risk(current_step.tool_hint)
    
    if risk_level != RiskLevel.HIGH:
        # LOW-risk tools don't require approval - skip this node
        return {"plan": plan}

    # Pre-generate operation details for display during approval
    command_to_show = None
    path_to_show = None
    file_path_to_show = None
    file_content_to_show = None
    code_to_show = None
    port_to_show = None
    synthesis_preview_to_show = None
    browser_task_to_show = None

    workspace_path = state.get("workspace_path") or ""

    if current_step.tool_hint == "shell_command" and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            command_prompt = load_prompt("plan_execute", "approval_shell_command").format(**locals())

            llm = _pkg().get_llm()
            messages = [
                SystemMessage(content=load_prompt("plan_execute", "approval_shell_command_system")),
                HumanMessage(content=command_prompt),
            ]
            response = llm.invoke(messages)
            command_to_show = response.content.strip()
            if command_to_show.startswith("```"):
                lines = command_to_show.split("\n")
                command_to_show = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()
            # Store the command in the step so shell_node can use it
            current_step.result = f"_PENDING_COMMAND: {command_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate command for approval: {e}")
            command_to_show = "(command generation failed)"

    elif current_step.tool_hint == "delete_file" and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            delete_prompt = load_prompt("plan_execute", "approval_delete_file").format(**locals(), _prompt_today=date.today().isoformat())

            llm = _pkg().get_llm()
            messages = [
                SystemMessage(content=load_prompt("plan_execute", "approval_delete_file_system")),
                HumanMessage(content=delete_prompt),
            ]
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            data = json.loads(raw)
            path_to_show = data.get("path", "")
            # Store the path in the step so delete_file_node can use it
            current_step.result = f"_PENDING_PATH: {path_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate path for approval: {e}")
            path_to_show = "(path generation failed)"

    elif current_step.tool_hint in ("write_file", "file_editor") and workspace_path:
        try:
            context_block = _build_coding_context(plan, current_step)
            file_prompt = load_prompt("plan_execute", "approval_write_file").format(**locals(), _prompt_today=date.today().isoformat())

            llm = _pkg().get_llm()
            messages = [
                SystemMessage(content=load_prompt("plan_execute", "approval_write_file_system")),
                HumanMessage(content=file_prompt),
            ]
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            data = json.loads(raw)
            file_path_to_show = data.get("path", "")
            # Store the path in the step so write_file_node can use it
            current_step.result = f"_PENDING_FILE_PATH: {file_path_to_show}"
        except Exception as e:
            print(f"⚠️ Failed to generate file path for approval: {e}")
            file_path_to_show = "(file path generation failed)"

    elif current_step.tool_hint in ("browser_use", "browser-use"):
        browser_task_to_show = current_step.task

    elif current_step.tool_hint not in (
        "web_search", "tavily_search", "code_executor", "none",
        "setup_workspace", "shell_command", "start_server", "browser_use", "browser-use",
    ) and current_step.tool_hint not in ("write_file", "file_editor", "delete_file"):
        # Unrecognized tool_hint -> synthesis will handle this step (see
        # graph.py routing). Preview via declare_schema ONLY (not the full
        # generate+validate pipeline) — running full synthesis here just to
        # preview it would mean paying for codegen+sandbox validation TWICE
        # (once to show, once for real in synthesize_tool_node) and risks
        # showing the human one generated function while a DIFFERENT one
        # (from a second, independent LLM call) actually executes — exactly
        # the command/execution mismatch the pre-generation pattern elsewhere
        # in this function exists to prevent. The schema declaration alone
        # (capability name, description, I/O shapes) is cheap, deterministic
        # enough to be a fair preview, and gives a human real signal on what
        # kind of code is about to be generated and run.
        try:
            import json as _json

            context_block = _build_coding_context(plan, current_step)
            llm = _pkg().get_llm()
            schema = _pkg().declare_schema(plan.goal, current_step.task, context_block, llm, registry=default_registry)
            synthesis_preview_to_show = (
                f"Will synthesize a new tool: {schema.capability_name}\n"
                f"  {schema.description}\n"
                f"  Input: {schema.input_description}\n"
                f"  Output: {schema.output_description}"
            )
            # Cache the declared schema so synthesize_tool_node reuses THIS
            # exact declaration instead of calling declare_schema again —
            # same reuse pattern as _PENDING_COMMAND/_PENDING_FILE_PATH above.
            current_step.result = f"_PENDING_SCHEMA: {_json.dumps(schema.model_dump())}"
        except Exception as e:
            print(f"⚠️ Failed to preview synthesis for approval: {e}")
            synthesis_preview_to_show = "(synthesis preview generation failed)"

    # Trigger interrupt for HIGH-risk operations
    approval_request = {
        "type": "command_approval",
        "tool": current_step.tool_hint,
        "step_id": current_step.id,
        "task": current_step.task,
        "risk_level": "HIGH",
        "command": command_to_show,
        "path": path_to_show,
        "file_path": file_path_to_show,
        "synthesis_preview": synthesis_preview_to_show,
        "browser_task": browser_task_to_show,
        "workspace_path": workspace_path,
    }
    
    # Call interrupt to pause execution and wait for human input
    human_response = interrupt(approval_request)
    
    # Process human's response after resume
    decision = human_response.get("decision", "reject")
    
    if decision == "approve":
        # Human approved - proceed with tool execution
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "approve",
            "timestamp": date.today().isoformat(),
        }
        print(f"✅ Human approved: {current_step.tool_hint} for step {current_step.id}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    elif decision == "reject":
        # Human rejected - mark step as FAILED and route to replanner
        current_step.status = StepStatus.FAILED
        current_step.error = "Operation rejected by human"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "reject",
            "timestamp": date.today().isoformat(),
        }
        print(f"❌ Human rejected: {current_step.tool_hint} for step {current_step.id}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    elif decision == "alternative":
        # Human provided alternative input - use it for tool execution
        alternative_input = human_response.get("alternative_input", "")
        # Store alternative in step result for the tool node to use
        current_step.result = f"ALTERNATIVE_INPUT: {alternative_input}"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "alternative",
            "alternative_input": alternative_input,
            "timestamp": date.today().isoformat(),
        }
        print(f"🔄 Human provided alternative for step {current_step.id}: {alternative_input[:100]}")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
    
    else:
        # Unknown decision - treat as reject for safety
        current_step.status = StepStatus.FAILED
        current_step.error = f"Unknown approval decision: {decision}"
        approval_event = {
            "step_id": current_step.id,
            "tool": current_step.tool_hint,
            "decision": "reject",
            "reason": f"Unknown decision: {decision}",
            "timestamp": date.today().isoformat(),
        }
        print(f"❌ Unknown decision '{decision}' - treating as reject")
        return {
            "plan": plan,
            "approval_events": [approval_event],
        }
