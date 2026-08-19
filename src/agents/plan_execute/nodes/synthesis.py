"""Tool synthesis and final-answer synthesis nodes."""

import time

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig

from src.synthesis.registry import default_registry
from src.synthesis.schema import SynthesizedTool
from src.agents.prompts.loader import load_prompt
from .common import _pkg
from ..state import State, StepStatus
from .common import _build_coding_context, _emit_synthesis_event

def synthesize_tool_node(state: State) -> dict:
    """
    Handle a step whose tool_hint matched no fixed tool (tool_hint='synthesize_tool').

    WHEN TO USE (triggered automatically by graph routing):
    - When the planner requests a capability not in the fixed tool registry
    - When a step's tool_hint doesn't match any standard tool
    - When reusable functionality is needed across multiple steps
    - For specialized calculations, transformations, or integrations
    - When the same logic needs to be applied to different inputs repeatedly

    WHEN NOT TO USE:
    - For one-off calculations (use code_executor instead)
    - When standard tools suffice (search, shell, file operations)
    - For simple operations that don't need reusability
    - When the task can be accomplished with existing fixed tools

    EXAMPLES of synthesized capabilities:
    - "convert_temperature_units" - Reusable temperature conversion
    - "fetch_exchange_rate" - Currency rate fetching with caching
    - "calculate_business_metrics" - Domain-specific calculations
    - "parse_custom_data_format" - Proprietary data format parsing
    - "apply_pricing_logic" - Business rule implementation

    WORKFLOW:
    1. Check if tool already exists in registry (reuse if found)
    2. If new tool needed, declare schema via LLM (input/output contract)
    3. Generate Python code implementation via LLM
    4. Validate code in sandbox (test with example input)
    5. Register successful tool for reuse across steps
    6. Execute tool with actual step input
    7. Return result or mark step FAILED if validation fails

    CAPABILITIES:
    - Dynamic tool creation based on step requirements
    - Tool registry for reuse across steps and runs
    - Schema-first approach (declare before implementation)
    - Sandbox validation for security
    - Automatic retry on validation failures
    - Integration with existing tool ecosystem

    SECURITY:
    - Code runs in sandboxed environment
    - No file I/O or network access (pure computation)
    - Standard library only (no external dependencies)
    - Validation before registration
    - Memory and timeout limits
    - HIGH-risk classification (requires approval)

    Previously these steps fell through to stub_node, which marked the step
    DONE with a placeholder message — silently pretending success when
    nothing actually happened. This node gives them a real path: check if a
    matching capability was already synthesized earlier in this run (reuse
    it directly, no new LLM calls), and if not, run the full synthesis
    pipeline (declare schema -> generate code -> validate in sandbox ->
    register) with retry-on-validation-failure, matching the same
    generate/validate/retry shape code_executor_node already uses.

    On success the step is marked DONE and the synthesized tool is invoked
    immediately to actually complete the step (not just registered for
    hypothetical future use — the step that triggered synthesis still needs
    its own result). On failure after exhausting retries, the step is
    marked FAILED and the existing replanner takes it from there — no new
    failure-handling logic needed, matching every other node in this file.

    See src/synthesis/__init__.py module docstring for the full pipeline
    rationale and the motivating temperature-conversion trace.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("synthesize_tool_node called with no plan in state")

    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("synthesize_tool_node called with no RUNNING step")

    context_block = _build_coding_context(plan, current_step)
    llm = _pkg().get_llm()

    # --- Step 1: declare the schema (or reuse if we've synthesized this
    # exact capability already earlier in the run) ---
    try:
        schema = _pkg().declare_schema(plan.goal, current_step.task, context_block, llm, registry=default_registry)
        _emit_synthesis_event(
            str(current_step.id),
            f"Schema: {schema.capability_name}",
            {
                "capability_name": schema.capability_name,
                "description": schema.description,
                "input_description": schema.input_description,
                "output_description": schema.output_description,
                "example_input": schema.example_input,
            },
            status="success",
        )
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = f"synthesize_tool_node: failed to declare schema: {e}"
        print(f"❌ Synthesis schema declaration failed: {e}")
        return {"plan": plan, "steps_executed": 1}

    existing = default_registry.get(schema.capability_name)
    if existing is not None:
        # Reuse: run the already-validated function against a FRESH input
        # relevant to this step (schema.example_input from THIS declaration
        # call reflects what THIS step actually needs, even though the
        # underlying capability/code is shared with an earlier step).
        result = _pkg().validate_synthesized_function(existing.source_code, schema)
        default_registry.mark_used(schema.capability_name)
        if result.success:
            current_step.status = StepStatus.DONE
            current_step.result = (
                f"[reused synthesized tool: {schema.capability_name}] {result.output}"
            )
            print(f"✅ Reused synthesized tool '{schema.capability_name}' (used {existing.times_used}x)")
        else:
            # The reused tool didn't handle this step's specific input —
            # fall through to synthesizing a fresh one below rather than
            # failing outright, since the capability name matching doesn't
            # guarantee the exact same input shape across different steps.
            print(f"⚠️ Reused tool '{schema.capability_name}' failed on this step's input, re-synthesizing: {result.error}")
            existing = None

    if existing is None:
        # --- Steps 2-4: generate, validate, retry on failure ---
        max_retries = 2
        last_error = None
        generated_code = None
        validation_result = None

        for attempt in range(max_retries + 1):
            try:
                generated_code = _pkg().generate_function_code(schema, llm, previous_error=last_error)
            except Exception as e:
                last_error = f"Code generation call failed: {e}"
                continue

            validation_result = _pkg().validate_synthesized_function(generated_code, schema)
            if validation_result.success:
                break
            last_error = validation_result.error

        if validation_result is None or not validation_result.success:
            current_step.status = StepStatus.FAILED
            current_step.error = (
                f"synthesize_tool_node: '{schema.capability_name}' failed validation "
                f"after {max_retries + 1} attempts: {last_error}"
            )
            print(f"❌ Synthesis failed after {max_retries + 1} attempts: {last_error}")
            return {"plan": plan, "steps_executed": 1}

        # --- Step 5: register ---
        tool = SynthesizedTool(
            capability_name=schema.capability_name,
            description=schema.description,
            input_description=schema.input_description,
            output_description=schema.output_description,
            source_code=generated_code,
            example_input=schema.example_input,
            example_output=validation_result.output,
        )
        default_registry.register(tool)
        default_registry.mark_used(schema.capability_name)

        current_step.status = StepStatus.DONE
        current_step.result = f"[synthesized new tool: {schema.capability_name}] {validation_result.output}"
        _emit_synthesis_event(
            str(current_step.id),
            f"Generated: {schema.capability_name}",
            {"source_code": generated_code, "example_output": validation_result.output},
            status="success",
        )
        print(f"✅ Synthesized and registered new tool '{schema.capability_name}'")
        print(f"   {schema.description}")

    return {"plan": plan, "steps_executed": 1}


def synthesize_node(state: State, config: RunnableConfig | None = None) -> dict:
    """
    Synthesize all step results into a final answer using the LLM.

    This node is called when all steps are complete and the final step has
    tool_hint="none". It concatenates all step results and asks the LLM to
    provide a comprehensive answer to the original goal.
    """
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("synthesize_node called with no plan in state")

    print(f"\n{'='*80}")
    print(f"🧠 Synthesizing Final Answer")
    print(f"{'='*80}")

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
    goal = plan.goal
    step_results_str = "\n".join(step_results)
    server_url_notice = f"\n✅ A dev server is running at: {state.get('server_url')}\n" if state.get('server_url') else ""
    synthesis_prompt = load_prompt("plan_execute", "final_synthesis").format(**locals())

    llm = _pkg().get_llm()
    messages = [
        SystemMessage(content=load_prompt("plan_execute", "final_synthesis_system")),
        HumanMessage(content=synthesis_prompt),
    ]

    tracker = None
    synthesis_step_id = None
    if config and "configurable" in config and "tracker" in config["configurable"]:
        tracker = config["configurable"]["tracker"]
        synthesis_step_id = f"{tracker.run_id}-synthesis"
        from src.api.models import RunStepEvent, StepPayload
        from src.api.models import utc_now_iso
        
        # Pre-emit the running step
        tracker.handle_event(
            RunStepEvent(
                run_id=tracker.run_id,
                step_id=synthesis_step_id,
                parent_step_id=None,
                arm=tracker.arm,
                type="synthesis",
                status="running",
                title="Synthesizing final answer",
                started_at=utc_now_iso(),
                payload=StepPayload(result=""),
            )
        )
    
    response_content = ""
    last_emit_time = time.monotonic()
    last_emit_len = 0

    try:
        for chunk in llm.stream(messages):
            if hasattr(chunk, "content"):
                response_content += chunk.content
            elif isinstance(chunk, str):
                response_content += chunk
                
            now = time.monotonic()
            # Throttle: emit only if >= 40 new chars or >= 0.15s elapsed
            if tracker and synthesis_step_id and (len(response_content) - last_emit_len >= 40 or now - last_emit_time >= 0.15):
                last_emit_time = now
                last_emit_len = len(response_content)
                from src.api.models import RunStepEvent, StepPayload
                from src.api.models import utc_now_iso
                tracker.handle_event(
                    RunStepEvent(
                        run_id=tracker.run_id,
                        step_id=synthesis_step_id,
                        parent_step_id=None,
                        arm=tracker.arm,
                        type="synthesis",
                        status="running",
                        title="Synthesizing final answer",
                        started_at=utc_now_iso(),
                        payload=StepPayload(result=response_content),
                    )
                )
    except Exception:
        # If stream fails or isn't supported, fall back to invoke
        response_content = ""

    if not response_content and hasattr(llm, "invoke"):
        resp = llm.invoke(messages)
        if hasattr(resp, "content"):
            response_content = resp.content
        elif isinstance(resp, str):
            response_content = resp

    # Store the synthesis result directly on the plan. This no longer depends
    # on a step having tool_hint="none" existing in the plan — the planner
    # prompt isn't guaranteed to always emit one, and when it doesn't, the
    # synthesized answer was previously silently discarded.
    plan.final_answer = response_content
    
    if tracker and synthesis_step_id:
        from src.api.models import RunStepEvent, StepPayload
        from src.api.models import utc_now_iso
        tracker.handle_event(
            RunStepEvent(
                run_id=tracker.run_id,
                step_id=synthesis_step_id,
                parent_step_id=None,
                arm=tracker.arm,
                type="synthesis",
                status="success",
                title="Synthesizing final answer",
                started_at=utc_now_iso(),
                ended_at=utc_now_iso(),
                payload=StepPayload(result=response_content),
            )
        )

    return {"plan": plan}
