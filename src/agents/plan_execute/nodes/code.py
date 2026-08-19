"""Code execution and workspace setup nodes."""

import json
from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage

from src.sandbox.shell_runner import make_project_workspace
from src.agents.prompts.loader import load_prompt
from .common import _log_approval, _pkg
from ..state import State, StepStatus

# Exception types that are typically fixable with small code adjustments
_FIXABLE_ERRORS = {
    "ImportError",
    "ModuleNotFoundError",
    "IndexError",
    "KeyError",
    "AttributeError",
    "TypeError",
    "NameError",
}


def _is_fixable_error(error_message: str) -> bool:
    """
    Determine if an error is likely fixable with a small code adjustment.
    Fixable errors are typically import issues, index/key errors, or simple type mismatches.
    Logical errors (ValueError, AssertionError, etc.) are not considered fixable.
    """
    for error_type in _FIXABLE_ERRORS:
        if error_type in error_message:
            return True
    return False


def code_executor_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "code_executor" — generates and runs Python code.

    WHEN TO USE:
    - For one-off calculations, data processing, or computational tasks
    - When you need to manipulate or analyze data from prior steps
    - For mathematical computations, statistical analysis, or data transformations
    - When standard library operations suffice (no external dependencies needed)
    - For generating test data, samples, or synthetic content
    - When the task is a single-use calculation (not needing reusability)

    WHEN NOT TO USE:
    - For reusable functionality across multiple steps (use synthesize_tool instead)
    - When the same logic needs to be applied to different inputs repeatedly
    - For file operations (use write_file_tool, delete_file_tool instead)
    - For network operations (use shell_command_tool or search instead)
    - When the task requires persistent tools or complex dependencies

    EXAMPLES:
    - "Calculate the compound interest for a loan over 5 years"
    - "Convert the temperature data from Celsius to Fahrenheit"
    - "Generate a list of 100 random numbers and calculate statistics"
    - "Parse the CSV data and filter rows where age > 25"
    - "Calculate the SHA-256 hash of a given string"
    - "Perform linear regression on the dataset and report the R-squared value"

    CAPABILITIES:
    - Full Python standard library access (math, json, re, datetime, etc.)
    - Automatic error detection and retry (up to 2 retries for fixable errors)
    - Sandbox execution with timeout (default: 15 seconds) and memory limits
    - Access to workspace files for reading/writing
    - Command-line argument support for dynamic input values
    - Comprehensive error reporting with stderr capture

    CONSTRAINTS:
    - No external package imports (standard library only)
    - No network access (security restriction)
    - No interactive input() calls (non-interactive execution)
    - Timeout enforced (prevents infinite loops)
    - Memory limits prevent resource exhaustion
    - Results must be printed to stdout for capture

    WORKFLOW:
    1. Analyze step task and prior context
    2. Determine if command-line arguments are needed
    3. Generate Python code via LLM
    4. Execute in sandboxed environment
    5. Capture stdout/stderr and handle errors
    6. Retry on fixable errors (import errors, syntax errors, etc.)
    7. Mark step DONE with result or FAILED with error

    This node:
    1. Uses the LLM to generate Python code based on the step's task description
    2. Executes the code in the sandbox (subprocess isolation, timeout, memory limits)
    3. Auto-retries for fixable errors (import errors, index errors, etc.) up to 2 times
    4. Marks the step DONE with the result (stdout) or error message

    The code generation LLM is given:
    - The current step's task description
    - Prior DONE step results for context
    - Instructions to print results to stdout for capture
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("code_executor_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("code_executor_node called with no RUNNING step")

    # Run generated code from inside the actual project workspace, not the
    # sandbox's own throwaway scratch dir — otherwise a script that reads or
    # writes a file previously created by write_file (or read/deleted by any
    # other workspace-aware tool) can't find it, since it's looking in a
    # directory that has nothing to do with where that file actually lives.
    workspace_path = state.get("workspace_path") or None

    try:
        # Build context from prior DONE steps
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

        # Determine whether this step needs concrete command-line argument
        # values (e.g. "take n as input" -> the script reads sys.argv[1]).
        # Without this, the generated code has nowhere to actually get a
        # real value from — _pkg().run_in_sandbox() supports an `args` list, but
        # someone has to decide what goes in it. We ask the LLM the same
        # way approval_node pre-generates commands/paths: a small, focused
        # call before the main code-generation call.
        script_args: list[str] = []
        try:
            args_prompt = load_prompt("plan_execute", "code_executor_args").format(**locals())

            args_llm = _pkg().get_llm()
            args_response = args_llm.invoke([
                SystemMessage(content=load_prompt("plan_execute", "code_executor_args_system")),
                HumanMessage(content=args_prompt),
            ])
            raw_args = args_response.content.strip()
            if raw_args.startswith("```"):
                lines = raw_args.split("\n")
                raw_args = "\n".join(line for line in lines if not line.startswith("```")).strip()
            import json
            args_data = json.loads(raw_args)
            script_args = [str(a) for a in args_data.get("args", [])]
        except Exception as e:
            # Fall back to no args rather than failing the whole step —
            # the generated code still has its own hardcoded-default
            # fallback per the prompt instructions below.
            print(f"⚠️ Failed to determine script args, proceeding with none: {e}")
            script_args = []

        args_note = (
            f"This script will be invoked with sys.argv[1:] = {script_args!r}. "
            f"Read the needed value(s) from sys.argv at those positions."
            if script_args
            else "This script will be invoked with no command-line arguments."
        )

        code_generation_prompt = load_prompt("plan_execute", "code_executor").format(**locals())

        llm = _pkg().get_llm()
        
        # Generate code with auto-retry for fixable errors
        max_retries = 2
        generated_code = None
        last_error = None
        
        for attempt in range(max_retries + 1):
            messages = [
                SystemMessage(content=load_prompt("plan_execute", "code_executor_system")),
                HumanMessage(content=code_generation_prompt),
            ]
            
            if attempt > 0:
                # Add error context to help fix the code
                messages[-1] = HumanMessage(
                    content=code_generation_prompt + load_prompt("plan_execute", "code_executor_retry").format(**locals())
                )
            
            response = llm.invoke(messages)
            generated_code = response.content.strip()
            
            # Remove markdown fences if present
            if generated_code.startswith("```"):
                lines = generated_code.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                generated_code = "\n".join(lines).strip()
            
            # Execute the code in the sandbox
            result = _pkg().run_in_sandbox(
                generated_code,
                timeout_seconds=15,
                memory_limit_mb=256,
                args=script_args,
                cwd=workspace_path,
            )
            
            if result.success:
                # Code executed successfully
                current_step.status = StepStatus.DONE
                current_step.result = result.stdout if result.stdout else "Code executed successfully with no output."
                print(f"✅ Code executed successfully")
                print(f"👁️  Result: {current_step.result[:300]}{'...' if len(current_step.result) > 300 else ''}")
                return {"plan": plan, "steps_executed": 1}
            else:
                # Code execution failed
                last_error = result.error or result.stderr or "Unknown error"
                print(f"❌ Code execution failed (attempt {attempt + 1}/{max_retries + 1}): {last_error[:200]}")
                
                # Check if this is a fixable error
                if _is_fixable_error(last_error) and attempt < max_retries:
                    # Retry with error context
                    print(f"🔄 Retrying with error context...")
                    continue
                else:
                    # Either not fixable or out of retries. This step never
                    # actually succeeded — it must be FAILED, not DONE.
                    # Previously this was marked DONE with the error text
                    # stuffed into .result, which meant: (a) _route_after_tool
                    # never saw a FAILED status, so the replanner never
                    # engaged for a code-exec failure, and (b) synthesize_node
                    # had no way to distinguish "this is the answer" from
                    # "this is an error message that happens to live in the
                    # result field" — a failed step could silently read as a
                    # legitimate finding in the final answer.
                    current_step.status = StepStatus.FAILED
                    error_message = f"Code execution failed: {last_error}"
                    if result.stdout:
                        error_message += f"\nStdout: {result.stdout}"
                    if result.stderr:
                        error_message += f"\nStderr: {result.stderr}"
                    current_step.error = error_message
                    current_step.result = error_message
                    return {"plan": plan, "steps_executed": 1}
        
        # Should not reach here, but handle gracefully. Same reasoning as
        # above — retries exhausted with no success means this step FAILED.
        current_step.status = StepStatus.FAILED
        final_error = f"Code execution failed after {max_retries + 1} attempts. Last error: {last_error}"
        current_step.error = final_error
        current_step.result = final_error
        return {"plan": plan, "steps_executed": 1}
        
    except Exception as e:
        # An exception in the node itself (not the sandboxed code) is also a
        # genuine failure, not a completed step.
        current_step.status = StepStatus.FAILED
        error_message = f"Code executor node error: {str(e)}"
        current_step.error = error_message
        current_step.result = error_message
        return {"plan": plan, "steps_executed": 1}



def setup_workspace_node(state: State) -> dict:
    """
    Execute a step whose tool_hint is "setup_workspace" — creates a project directory.

    WHEN TO USE:
    - As the FIRST step in any app/coding task
    - When creating a new project structure
    - Before scaffolding, file creation, or development work
    - When the task requires a dedicated working directory
    - For organizing project files and keeping workspace clean

    WHEN NOT TO USE:
    - When a workspace already exists (check state first)
    - For simple file operations that don't need a project structure
    - When working with temporary files (use temp directories instead)
    - For operations that don't require file system organization

    EXAMPLES:
    - "Create a new React project workspace"
    - "Set up a Python project directory structure"
    - "Initialize a workspace for the web application"
    - "Create a project folder for the new API"
    - "Set up a directory for the data processing pipeline"

    CAPABILITIES:
    - Creates timestamped workspace directories
    - Manages workspace lifecycle across steps
    - Prevents workspace conflicts between runs
    - Provides clean slate for each new project
    - Integrates with all file and shell operations
    - Automatic workspace path management

    WORKFLOW:
    1. Check if workspace already exists in state
    2. Create new workspace directory with timestamp
    3. Store workspace path in state for subsequent steps
    4. Make workspace available to all file/shell operations
    5. Workspace persists until task completion or cleanup

    INTEGRATION:
    - File operations (write_file_tool, delete_file_tool) use this workspace
    - Shell commands (shell_command_tool) run in this workspace
    - Code execution (code_executor_node) has access to workspace files
    - Dev server (start_server_tool) runs from this workspace
    - Provides consistent working directory across all project steps

    SAFETY:
    - Workspace isolation prevents file conflicts
    - Timestamped directories prevent overwriting
    - Scoped to current task/run only
    - Automatic cleanup on task completion
    - No access to files outside workspace
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("setup_workspace_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("setup_workspace_node called with no RUNNING step")

    # Log LOW-risk operation
    log_update = _log_approval(state, "setup_workspace", current_step.task)

    # Derive a slug from the goal for a human-readable directory name
    slug = "-".join(plan.goal.lower().split()[:4])
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)[:40]

    workspace_path = make_project_workspace(slug)

    current_step.status = StepStatus.DONE
    current_step.result = f"Project workspace created at: {workspace_path}"
    print(f"✅ Workspace created: {workspace_path}")

    return {"plan": plan, "steps_executed": 1, "workspace_path": workspace_path, **log_update}
