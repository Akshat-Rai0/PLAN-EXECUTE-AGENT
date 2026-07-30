import asyncio
import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.browser_pipelines.data_collection import plan_sources
from .models import ComparisonItem, ComparisonResult

def build_comparison_table(results: list[dict]) -> str:
    """Build a deterministic markdown comparison table from structured results."""
    if not results:
        return "No data extracted for comparison."
        
    # Find all unique attributes across all results
    all_keys = set()
    for res in results:
        data = res.get("data")
        if isinstance(data, dict):
            all_keys.update(data.keys())
            
    # Remove 'raw_text' or 'raw' if present as a fallback
    all_keys.discard("raw_text")
    all_keys.discard("raw")
            
    if not all_keys:
        return "Failed to extract structured attributes for comparison."
        
    keys = sorted(list(all_keys))
    
    # Markdown table header
    header = "| Source | " + " | ".join(keys) + " |"
    divider = "|---|" + "|".join(["---" for _ in keys]) + "|"
    
    rows = []
    for res in results:
        url = res.get("url", "Unknown")
        data = res.get("data") or {}
        row_cells = []
        for k in keys:
            val = str(data.get(k, "N/A")).replace("|", "\\|").replace("\n", " ")
            row_cells.append(val)
        row = f"| {url} | " + " | ".join(row_cells) + " |"
        rows.append(row)
        
    return "\n".join([header, divider] + rows)

async def _extract_compare_tab(browser_tool: BrowserTool, url: str, extraction_goal: str) -> dict:
    """Run extraction in a separate context of the shared browser instance."""
    from browser_use import Agent
    
    prompt = f"""You have VISION capabilities - you can SEE the page visually.

Navigate to {url} and extract the following comparable attributes: {extraction_goal}.
For each item found, extract:
- "title": product/item title
- "price": price as a number
- "attributes": object with key attributes for comparison
- "source": the website/platform name
- "url": full URL to the item
- "condition": condition (New, Used, Refurbished, etc) if applicable

Return ONLY a JSON object mapping attributes to values, no markdown.
Use vision to identify pricing, titles, and attributes visually.
"""
    
    # We use the existing browser instance so it runs in a new context of the same browser side-by-side
    agent = Agent(
        task=prompt,
        llm=browser_tool._llm,
        browser=browser_tool._browser,
        max_actions_per_step=4,
        use_vision=True
    )
    
    try:
        history = await asyncio.wait_for(agent.run(), timeout=120)
        result_text = history.final_result() if history else None
        
        if result_text:
            text = result_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            data = json.loads(text)
            # Convert to ComparisonItem if it's a single item, or wrap in list if multiple
            if isinstance(data, dict) and "title" in data:
                return {"url": url, "data": ComparisonItem(**data).model_dump()}
            elif isinstance(data, list):
                items = [ComparisonItem(**item) for item in data if isinstance(item, dict)]
                return {"url": url, "data": [item.model_dump() for item in items]}
            return {"url": url, "data": data}
    except json.JSONDecodeError:
        return {"url": url, "data": {"raw_text": result_text}}
    except Exception as e:
        return {"url": url, "data": None, "error": str(e)}
            
    return {"url": url, "data": None, "error": "Failed to extract data"}


async def run_comparison_pipeline(browser_tool: BrowserTool, task: str, targets: list[str], extraction_goal: str) -> BrowserToolResult:
    """End-to-end comparison pipeline running across multiple tabs concurrently with structured output."""
    await browser_tool._ensure_browser()
    browser_tool._ensure_llm()
    
    urls = plan_sources(task, targets)
    if not urls:
        urls = targets if targets else []
        if not urls:
            result = ComparisonResult(
                items=[],
                best_match=None,
                criteria=extraction_goal,
                search_query=task
            )
            return BrowserToolResult(
                success=False, 
                status=ActionStatus.FAILED, 
                error="No valid sources found for comparison",
                metadata={"structured_result": result.model_dump()}
            )
            
    tasks = [_extract_compare_tab(browser_tool, url, extraction_goal) for url in urls]
    outputs = await asyncio.gather(*tasks)
    
    # Extract only successful ones and flatten to ComparisonItem list
    all_items = []
    for output in outputs:
        data = output.get("data")
        if data:
            if isinstance(data, dict) and "title" in data:
                all_items.append(ComparisonItem(**data))
            elif isinstance(data, list):
                all_items.extend([ComparisonItem(**item) for item in data if isinstance(item, dict)])
    
    if not all_items:
        result = ComparisonResult(
                items=[],
                best_match=None,
                criteria=extraction_goal,
                search_query=task
            )
        return BrowserToolResult(
            success=False, 
            status=ActionStatus.FAILED, 
            error="Failed to extract comparison data from any source",
            metadata={"structured_result": result.model_dump()}
        )
    
    # Build structured result
    # Simple best match logic: lowest price
    best_match = min(all_items, key=lambda x: x.price) if all_items else None
    
    structured_result = ComparisonResult(
        items=[item.model_dump() for item in all_items],
        best_match=best_match.model_dump() if best_match else None,
        criteria=extraction_goal,
        search_query=task
    )
    
    # Also build table for human-readable output
    table = build_comparison_table([{"url": item.source, "data": item.model_dump()} for item in all_items])
    
    return BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text=table,
        metadata={
            "structured_result": structured_result.model_dump(),
            "raw_results": outputs
        }
    )
