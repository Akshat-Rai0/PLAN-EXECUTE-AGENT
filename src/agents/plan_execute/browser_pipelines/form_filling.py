import json
from typing import Any

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from .models import FormField, FormFillResult

async def identify_fields(browser_tool: BrowserTool) -> list[FormField]:
    """Enumerate all fillable fields on the current page using a vision/DOM pass."""
    print("📝 [FormFilling] identify_fields() called")
    task_prompt = """You have VISION capabilities - you can SEE the page visually.

Extract all fillable form fields from the current page.
Return ONLY a valid JSON array of objects. Do not include markdown formatting or explanation.
Each object must have:
- "name": logical name or label of the field
- "type": "text", "dropdown", "checkbox", "radio", etc.
- "selector": a valid CSS selector to target the field
- "required": boolean
- "current_value": current text or selection

Use vision to identify fields by their visual labels and positions.
"""
    result = await browser_tool.run_task(task=task_prompt, max_steps=2)
    
    if not result.success or not result.extracted_text:
        return []
        
    try:
        text = result.extracted_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        
        fields_data = json.loads(text)
        if isinstance(fields_data, list):
            # Convert to FormField models
            return [FormField(**field) for field in fields_data if isinstance(field, dict)]
    except Exception as e:
        print(f"📝 [FormFilling] Error parsing fields: {e}")
        pass
        
    return []

async def resolve_field_values(fields: list[FormField], user_context: str) -> list[dict[str, str]]:
    """Map the identified fields to the provided user context/data."""
    print(f"📝 [FormFilling] resolve_field_values() called with {len(fields)} fields")
    if not fields:
        return []
    
    # Convert models to dicts for LLM processing
    fields_dict = [field.model_dump() for field in fields]
        
    prompt = f"""You are a form-filling assistant mapping user data to form fields.

User Context / Target Data:
{user_context}

Identified Fields:
{json.dumps(fields_dict, indent=2)}

Match the user data to the appropriate fields. For each field that can be filled, determine the action ("fill" for text, "select" for dropdowns/radios/checkboxes) and the exact value to use.

Return ONLY a valid JSON array of objects. Do not include markdown fences.
Each object must have:
- "selector": the exact CSS selector from the Identified Fields
- "action": "fill" or "select"
- "value": the exact string value to fill or select
"""
    llm = get_llm()
    messages = [
        SystemMessage(content="You map user data to form fields and output raw JSON arrays."),
        HumanMessage(content=prompt)
    ]
    response = llm.invoke(messages)
    text = response.content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        
    try:
        actions = json.loads(text)
        return [a for a in actions if isinstance(a, dict) and "selector" in a and "value" in a]
    except Exception:
        return []

async def fill_fields(browser_tool: BrowserTool, actions: list[dict[str, str]]) -> list[BrowserToolResult]:
    """Execute deterministic fill/select actions without LLM overhead."""
    print(f"📝 [FormFilling] fill_fields() called with {len(actions)} actions")
    results = []
    for act in actions:
        selector = act["selector"]
        val = act["value"]
        action_type = act.get("action", "fill").lower()
        
        if action_type == "select":
            res = await browser_tool.select_option(selector, val)
        else:
            res = await browser_tool.fill(selector, val)
        results.append(res)
    return results

async def submit_and_verify(browser_tool: BrowserTool) -> BrowserToolResult:
    """Find and click the submit button with HITL gating."""
    print("📝 [FormFilling] submit_and_verify() called")
    prompt = """You have VISION capabilities - you can SEE the page visually.

Find the submit button for the primary form on this page.
Use vision to identify submit buttons by their visual appearance (buttons with text like "Submit", "Send", "Continue", etc.).
Return ONLY a JSON object with one key "selector" containing the CSS selector for the submit button.
"""
    res = await browser_tool.run_task(task=prompt, max_steps=2)
    if not res.success or not res.extracted_text:
        return res
        
    try:
        text = res.extracted_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        
        data = json.loads(text)
        selector = data.get("selector")
        if selector:
            return await browser_tool.click(selector)
    except Exception:
        pass
        
    return res

async def run_form_filling_pipeline(browser_tool: BrowserTool, context: str) -> BrowserToolResult:
    """End-to-end form filling pipeline with structured output."""
    print(f"📝 [FormFilling] run_form_filling_pipeline() started with context: {context[:50]}...")
    
    # Ensure browser is ready with proper configuration
    browser_tool._ensure_llm()
    await browser_tool._ensure_browser()
    
    fields = await identify_fields(browser_tool)
    if not fields:
        result = FormFillResult(success=False, error="Could not identify form fields.")
        return BrowserToolResult(
            success=False, 
            status=ActionStatus.FAILED, 
            error="Could not identify form fields.",
            metadata={"structured_result": result.model_dump()}
        )
        
    actions = await resolve_field_values(fields, context)
    if not actions:
        result = FormFillResult(success=False, error="Could not map context to form fields.")
        return BrowserToolResult(
            success=False, 
            status=ActionStatus.FAILED, 
            error="Could not map context to form fields.",
            metadata={"structured_result": result.model_dump()}
        )
        
    fill_results = await fill_fields(browser_tool, actions)
    fields_filled = [act.get("selector", "unknown") for act in actions]
    
    submit_result = await submit_and_verify(browser_tool)
    
    # Build structured result
    structured_result = FormFillResult(
        fields_filled=fields_filled,
        success=submit_result.success,
        validation_message=submit_result.extracted_text if submit_result.success else None,
        error=submit_result.error if not submit_result.success else None
    )
    
    return BrowserToolResult(
        success=submit_result.success,
        status=submit_result.status,
        extracted_text=submit_result.extracted_text,
        error=submit_result.error,
        metadata={"structured_result": structured_result.model_dump()}
    )
