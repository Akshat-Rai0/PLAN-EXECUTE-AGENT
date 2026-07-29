import asyncio
import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus

def plan_sources(task: str, targets: list[str]) -> list[str]:
    """Determine which URLs to pull data from based on targets or trusted sources."""
    # If explicit URLs are provided, use them
    if targets and "user-specified" not in [str(t).lower() for t in targets]:
        # Filter for actual URLs vs general site names, for simplicity assuming valid strings
        return targets
    
    # Fallback to trusted sources
    from src.agents.plan_execute.nodes import _detect_trusted_topic, TRUSTED_SOURCES
    topic = _detect_trusted_topic(task)
    if topic and topic in TRUSTED_SOURCES:
        sources = TRUSTED_SOURCES[topic]
        # TRUSTED_SOURCES will be updated to hold tuples of (name, url, supported_tasks)
        return [s[1] for s in sources if len(s) > 2 and "data_collection" in s[2]]
    
    return []

async def _extract_from_url(url: str, extraction_goal: str) -> dict:
    """Run a single subagent on a URL to extract data using vision-based extraction."""
    tool = BrowserTool()
    await tool.navigate(url)
    
    prompt = f"Extract the following information from this page: {extraction_goal}. Return ONLY a valid JSON object containing the extracted data, no markdown."
    res = await tool.run_task(task=prompt, max_steps=2)
    await tool.close_session()
    
    if res.success and res.extracted_text:
        try:
            text = res.extracted_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            return {"url": url, "data": json.loads(text)}
        except Exception:
            return {"url": url, "data": {"raw_text": res.extracted_text}}
    return {"url": url, "data": None, "error": res.error}

async def spawn_subagents(urls: list[str], extraction_goal: str) -> list[dict]:
    """Spawn concurrent extraction subagents for each URL."""
    tasks = [_extract_from_url(url, extraction_goal) for url in urls]
    return await asyncio.gather(*tasks)

def aggregate_results(subagent_outputs: list[dict]) -> dict:
    """Merge subagent outputs into one structured object, flagging issues."""
    aggregated = {"results": [], "failed_urls": [], "conflicts": []}
    for out in subagent_outputs:
        if out.get("error") or out.get("data") is None:
            aggregated["failed_urls"].append(out["url"])
        else:
            aggregated["results"].append({"url": out["url"], "data": out["data"]})
            
    # Basic conflict detection stub (can be extended with LLM semantic comparison)
    # For now just bundles results.
    return aggregated

async def run_data_collection_pipeline(task: str, targets: list[str], extraction_goal: str) -> BrowserToolResult:
    """End-to-end data collection pipeline."""
    urls = plan_sources(task, targets)
    if not urls:
        # Try to treat targets as URLs if detection failed
        urls = targets if targets else []
        if not urls:
            return BrowserToolResult(success=False, status=ActionStatus.FAILED, error="No valid sources found for data collection.")
        
    outputs = await spawn_subagents(urls, extraction_goal)
    final_data = aggregate_results(outputs)
    
    success = len(final_data["results"]) > 0
    return BrowserToolResult(
        success=success,
        status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
        extracted_text=json.dumps(final_data, indent=2)
    )
