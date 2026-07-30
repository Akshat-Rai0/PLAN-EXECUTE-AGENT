import asyncio
import json

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from .models import DataPoint, CollectionResult

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
    print(f"📊 [DataCollection] _extract_from_url() from {url}")
    tool = BrowserTool()
    tool._ensure_llm()
    await tool.navigate(url)
    
    prompt = f"""You have VISION capabilities - you can SEE the page visually.

Extract the following information from this page: {extraction_goal}.
Return ONLY a valid JSON object containing the extracted data, no markdown.
Use vision to identify and extract the relevant information visually.
"""
    res = await tool.run_task(task=prompt, max_steps=2)
    await tool.close_session()
    
    if res.success and res.extracted_text:
        try:
            text = res.extracted_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            data = json.loads(text)
            return {"url": url, "data": data}
        except Exception as e:
            print(f"📊 [DataCollection] Error parsing data from {url}: {e}")
            return {"url": url, "data": {"raw_text": res.extracted_text}}
    return {"url": url, "data": None, "error": res.error}

async def spawn_subagents(urls: list[str], extraction_goal: str) -> list[dict]:
    """Spawn concurrent extraction subagents for each URL."""
    print(f"📊 [DataCollection] spawn_subagents() for {len(urls)} URLs")
    tasks = [_extract_from_url(url, extraction_goal) for url in urls]
    return await asyncio.gather(*tasks)

def aggregate_results(subagent_outputs: list[dict]) -> dict:
    """Merge subagent outputs into one structured object, flagging issues."""
    print(f"📊 [DataCollection] aggregate_results() from {len(subagent_outputs)} outputs")
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
    """End-to-end data collection pipeline with structured output."""
    print(f"📊 [DataCollection] run_data_collection_pipeline() started for task: {task[:50]}...")
    urls = plan_sources(task, targets)
    if not urls:
        # Try to treat targets as URLs if detection failed
        urls = targets if targets else []
        if not urls:
            result = CollectionResult(
                points=[],
                failed_urls=[],
                aggregated_data={},
                extraction_goal=extraction_goal
            )
            return BrowserToolResult(
                success=False, 
                status=ActionStatus.FAILED, 
                error="No valid sources found for data collection",
                metadata={"structured_result": result.model_dump()}
            )
        
    outputs = await spawn_subagents(urls, extraction_goal)
    final_data = aggregate_results(outputs)
    
    # Convert to DataPoint models
    points = []
    for result in final_data["results"]:
        point = DataPoint(
            url=result["url"],
            data=result["data"],
            confidence=1.0
        )
        points.append(point)
    
    # Build aggregated data (simple merge for now)
    aggregated_data = {}
    for point in points:
        aggregated_data[point.url] = point.data
    
    structured_result = CollectionResult(
        points=[p.model_dump() for p in points],
        failed_urls=final_data["failed_urls"],
        aggregated_data=aggregated_data,
        extraction_goal=extraction_goal
    )
    
    success = len(points) > 0
    return BrowserToolResult(
        success=success,
        status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
        extracted_text=json.dumps(final_data, indent=2),
        metadata={"structured_result": structured_result.model_dump()}
    )
