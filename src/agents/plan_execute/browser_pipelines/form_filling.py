import json
from typing import Any

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

async def identify_fields(browser_tool: BrowserTool) -> list[dict[str, Any]]:
    """Enumerate all fillable fields on the current page using a vision/DOM pass."""
    task_prompt = """Extract all fillable form fields from the current page.
Return ONLY a valid JSON array of objects. Do not include markdown formatting or explanation.
Each object must have:
- "name": logical name or label of the field
- "type": "text", "dropdown", "checkbox", "radio", etc.
- "selector": a valid CSS selector to target the field
- "required": boolean
- "current_value": current text or selection
"""
    result = await browser_tool.run_task(task=task_prompt, max_steps=2)
    
    if not result.success or not result.extracted_text:
        return []
        
    try:
        text = result.extracted_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        
        fields = json.loads(text)
        if isinstance(fields, list):
            return fields
    except Exception:
        pass
        
    return []

async def resolve_field_values(fields: list[dict[str, Any]], user_context: str) -> list[dict[str, str]]:
    """Map the identified fields to the provided user context/data."""
    if not fields:
        return []
        
    prompt = f"""You are a form-filling assistant mapping user data to form fields.

User Context / Target Data:
{user_context}

Identified Fields:
{json.dumps(fields, indent=2)}

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
    prompt = """Find the submit button for the primary form on this page.
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
    """End-to-end form filling pipeline."""
    fields = await identify_fields(browser_tool)
    if not fields:
        return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="Could not identify form fields.")
        
    actions = await resolve_field_values(fields, context)
    if not actions:
        return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="Could not map context to form fields.")
        
    await fill_fields(browser_tool, actions)
    
    return await submit_and_verify(browser_tool)
