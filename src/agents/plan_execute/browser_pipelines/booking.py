import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.plan_execute.browser_pipelines.data_collection import plan_sources
from src.agents.plan_execute.browser_pipelines.form_filling import run_form_filling_pipeline
from .models import BookingOption, BookingRecommendation

async def gather_options(browser_tool: BrowserTool, url: str, params: str) -> list[BookingOption]:
    """Reuse the browser agent to navigate and extract available booking options."""
    print(f"✈️ [Booking] gather_options() from {url}")
    await browser_tool.navigate(url)
    
    prompt = f"""You have VISION capabilities - you can SEE the page visually.

Search for the following booking parameters: {params}.
After the results load, extract the available options (price, duration, timing, provider, url) as a JSON array of objects.
Each object must have:
- "price": number
- "duration": string (optional)
- "timing": string (optional)
- "provider": string
- "url": string (optional)
- "attributes": object with any additional details

Return ONLY the JSON array, no markdown.
Use vision to identify pricing, timing, and provider information visually.
"""
    
    res = await browser_tool.run_task(task=prompt, max_steps=6)
    if res.success and res.extracted_text:
        try:
            text = res.extracted_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            options_data = json.loads(text)
            if isinstance(options_data, list):
                # Convert to BookingOption models
                return [BookingOption(**opt) for opt in options_data if isinstance(opt, dict)]
        except Exception as e:
            print(f"✈️ [Booking] Error parsing options: {e}")
    return []

async def reason_best_option(options: list[BookingOption], criteria: str) -> BookingRecommendation:
    """Use an LLM call to rank options against explicit criteria."""
    print(f"✈️ [Booking] reason_best_option() evaluating {len(options)} options")
    
    # Convert models to dicts for LLM processing
    options_dict = [opt.model_dump() for opt in options]
    
    prompt = f"""You are a booking assistant. Rank and recommend the best options from the provided list based on the user's criteria.

Options:
{json.dumps(options_dict, indent=2)}

Criteria:
{criteria}

If the user explicitly said "book the cheapest" or similar, select the single best option. 
Otherwise, present the top 3 with their tradeoffs.

Return your response as a JSON object with:
- "selected_option": the best option (full object)
- "alternatives": array of other good options (full objects)
- "reasoning": string explaining your choice
- "criteria": string repeating the criteria used
"""
    llm = get_llm()
    messages = [
        SystemMessage(content="You are a helpful travel and booking assistant. Output ONLY valid JSON, no markdown."),
        HumanMessage(content=prompt)
    ]
    response = llm.invoke(messages)
    
    try:
        text = response.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        data = json.loads(text)
        return BookingRecommendation(**data)
    except Exception as e:
        print(f"✈️ [Booking] Error parsing recommendation: {e}")
        # Fallback to text response
        return BookingRecommendation(
            selected_option=options[0] if options else None,
            alternatives=options[1:4] if len(options) > 1 else [],
            reasoning=response.content,
            criteria=criteria
        )

async def run_booking_pipeline(browser_tool: BrowserTool, task: str, targets: list[str]) -> BrowserToolResult:
    """End-to-end booking pipeline with structured output."""
    print(f"✈️ [Booking] run_booking_pipeline() started for task: {task[:50]}...")
    
    # Ensure browser is ready with proper configuration
    browser_tool._ensure_llm()
    await browser_tool._ensure_browser()
    
    # 1. Resolve site
    urls = plan_sources(task, targets)
    url = urls[0] if urls else (targets[0] if targets else None)
    
    if not url:
        result = BookingRecommendation(
            selected_option=None,
            alternatives=[],
            reasoning="No valid booking source found",
            criteria=task
        )
        return BrowserToolResult(
            success=False, 
            status=ActionStatus.FAILED, 
            error="No valid booking source found",
            metadata={"structured_result": result.model_dump()}
        )
        
    # 2. Gather options
    options = await gather_options(browser_tool, url, task)
    if not options:
        result = BookingRecommendation(
            selected_option=None,
            alternatives=[],
            reasoning="Failed to gather booking options",
            criteria=task
        )
        return BrowserToolResult(
            success=False, 
            status=ActionStatus.FAILED, 
            error="Failed to gather booking options",
            metadata={"structured_result": result.model_dump()}
        )
        
    # 3. Reason best option
    recommendation = await reason_best_option(options, task)
    
    # 4. If actual booking is requested, route to form filling pipeline
    if any(w in task.lower() for w in ["book", "buy", "purchase", "reserve"]):
        form_task = f"Book the selected option based on this recommendation: {recommendation.reasoning}"
        form_res = await run_form_filling_pipeline(browser_tool, form_task)
        # Append our recommendation context
        form_res.extracted_text = f"Recommendation:\n{recommendation.reasoning}\n\nBooking Result:\n{form_res.extracted_text or form_res.status.value}"
        # Update metadata with structured result
        if form_res.metadata:
            form_res.metadata["recommendation"] = recommendation.model_dump()
        return form_res
        
    # Otherwise just return the recommendation
    return BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text=recommendation.reasoning,
        metadata={
            "structured_result": recommendation.model_dump(),
            "options_extracted": len(options)
        }
    )
