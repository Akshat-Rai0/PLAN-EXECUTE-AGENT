import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.plan_execute.browser_pipelines.data_collection import plan_sources
from src.agents.plan_execute.browser_pipelines.form_filling import run_form_filling_pipeline

async def gather_options(browser_tool: BrowserTool, url: str, params: str) -> list[dict]:
    """Reuse the browser agent to navigate and extract available booking options."""
    await browser_tool.navigate(url)
    
    prompt = f"Search for the following booking parameters: {params}. After the results load, extract the available options (price, duration, timing, etc.) as a JSON array of objects. Return ONLY the JSON array."
    
    res = await browser_tool.run_task(task=prompt, max_steps=6)
    if res.success and res.extracted_text:
        try:
            text = res.extracted_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            options = json.loads(text)
            if isinstance(options, list):
                return options
        except Exception:
            pass
    return []

async def reason_best_option(options: list[dict], criteria: str) -> str:
    """Use an LLM call to rank options against explicit criteria."""
    prompt = f"""You are a booking assistant. Rank and recommend the best options from the provided list based on the user's criteria.

Options:
{json.dumps(options, indent=2)}

Criteria:
{criteria}

If the user explicitly said "book the cheapest" or similar, select the single best option. 
Otherwise, present the top 3 with their tradeoffs.
"""
    llm = get_llm()
    messages = [
        SystemMessage(content="You are a helpful travel and booking assistant."),
        HumanMessage(content=prompt)
    ]
    response = llm.invoke(messages)
    return response.content

async def run_booking_pipeline(browser_tool: BrowserTool, task: str, targets: list[str]) -> BrowserToolResult:
    """End-to-end booking pipeline."""
    # 1. Resolve site
    urls = plan_sources(task, targets)
    url = urls[0] if urls else (targets[0] if targets else None)
    
    if not url:
        return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="No valid booking source found.")
        
    # 2. Gather options
    options = await gather_options(browser_tool, url, task)
    if not options:
        return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="Failed to gather booking options.")
        
    # 3. Reason best option
    recommendation = await reason_best_option(options, task)
    
    # 4. If actual booking is requested, route to form filling pipeline
    if any(w in task.lower() for w in ["book", "buy", "purchase", "reserve"]):
        form_task = f"Book the selected option based on this recommendation: {recommendation}"
        form_res = await run_form_filling_pipeline(browser_tool, form_task)
        # Append our recommendation context
        form_res.extracted_text = f"Recommendation:\n{recommendation}\n\nBooking Result:\n{form_res.extracted_text or form_res.status.value}"
        return form_res
        
    # Otherwise just return the recommendation
    return BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text=recommendation,
        metadata={"options_extracted": len(options)}
    )
