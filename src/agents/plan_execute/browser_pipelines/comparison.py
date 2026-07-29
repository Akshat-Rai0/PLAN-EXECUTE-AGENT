import asyncio
import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.browser_pipelines.data_collection import plan_sources

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
    
    prompt = f"Navigate to {url} and extract the following comparable attributes: {extraction_goal}. Return ONLY a JSON object mapping attributes to values, no markdown."
    
    # We use the existing browser instance so it runs in a new context of the same browser side-by-side
    agent = Agent(
        task=prompt,
        llm=browser_tool._llm,
        browser=browser_tool._browser,
        max_actions_per_step=4
    )
    
    try:
        history = await asyncio.wait_for(agent.run(), timeout=120)
        result_text = history.final_result() if history else None
        
        if result_text:
            text = result_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            return {"url": url, "data": json.loads(text)}
    except json.JSONDecodeError:
        return {"url": url, "data": {"raw_text": result_text}}
    except Exception as e:
        return {"url": url, "data": None, "error": str(e)}
            
    return {"url": url, "data": None, "error": "Failed to extract data"}


async def run_comparison_pipeline(browser_tool: BrowserTool, task: str, targets: list[str], extraction_goal: str) -> BrowserToolResult:
    """End-to-end comparison pipeline running across multiple tabs concurrently."""
    await browser_tool._ensure_browser()
    browser_tool._ensure_llm()
    
    urls = plan_sources(task, targets)
    if not urls:
        urls = targets if targets else []
        if not urls:
            return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="No valid sources found for comparison.")
            
    tasks = [_extract_compare_tab(browser_tool, url, extraction_goal) for url in urls]
    outputs = await asyncio.gather(*tasks)
    
    # Extract only successful ones
    valid_results = [o for o in outputs if o.get("data")]
    
    if not valid_results:
        return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="Failed to extract comparison data from any source.")
        
    table = build_comparison_table(valid_results)
    
    return BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text=table,
        metadata={"raw_results": valid_results}
    )
