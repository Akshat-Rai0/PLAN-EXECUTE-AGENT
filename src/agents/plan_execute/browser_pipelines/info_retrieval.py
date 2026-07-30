from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from .models import InfoResult

async def run_info_retrieval_pipeline(browser_tool: BrowserTool, task: str, targets: list[str]) -> BrowserToolResult:
    """End-to-end information retrieval pipeline with structured output.
    
    Simpler than data collection: single trusted-source lookup, single-page read, single-answer synthesis.
    """
    
    # Ensure browser is ready with proper configuration
    browser_tool._ensure_llm()
    await browser_tool._ensure_browser()
    
    target_url = None
    if targets and "user-specified" not in [str(t).lower() for t in targets]:
        target_url = targets[0]
    else:
        from src.agents.plan_execute.nodes import _detect_trusted_topic, TRUSTED_SOURCES
        topic = _detect_trusted_topic(task)
        if topic and topic in TRUSTED_SOURCES:
            sources = TRUSTED_SOURCES[topic]
            for s in sources:
                if len(s) > 2 and "info_retrieval" in s[2]:
                    target_url = s[1]
                    break
            if not target_url and sources:
                target_url = sources[0][1] # fallback to first source
                
    if target_url:
        await browser_tool.navigate(target_url)
        prompt = f"""You have VISION capabilities - you can SEE the page visually.

Using this page as a starting point, find the answer to the following question or task: {task}

Return your answer as a JSON object with:
- "answer": the direct answer to the question
- "source_url": the URL where you found the answer
- "confidence": your confidence in this answer (0-1)
- "related_links": array of related URLs for context (optional)
- "query": the original query

Use vision to read the page content and identify the answer visually.
"""
    else:
        # No specific source, let the agent decide how to retrieve the info
        prompt = f"""You have VISION capabilities - you can SEE the page visually.

Find the answer to the following question or task: {task}

You may need to search for information first. Once you find the answer, return it as a JSON object with:
- "answer": the direct answer to the question
- "source_url": the URL where you found the answer
- "confidence": your confidence in this answer (0-1)
- "related_links": array of related URLs for context (optional)
- "query": the original query

Use vision to read page content and identify answers visually.
"""
    
    res = await browser_tool.run_task(task=prompt, max_steps=10)
    
    # Try to parse structured result
    structured_result = None
    if res.success and res.extracted_text:
        try:
            import json
            text = res.extracted_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            data = json.loads(text)
            structured_result = InfoResult(**data)
        except Exception as e:
            print(f"ℹ️ [InfoRetrieval] Error parsing structured result: {e}")
            # Fallback to unstructured result
            structured_result = InfoResult(
                answer=res.extracted_text,
                source_url=target_url or res.current_url or "unknown",
                confidence=0.7,
                related_links=[],
                query=task
            )
    else:
        structured_result = InfoResult(
            answer=res.error or "Failed to retrieve information",
            source_url=target_url or "unknown",
            confidence=0.0,
            related_links=[],
            query=task
        )
    
    return BrowserToolResult(
        success=res.success,
        status=res.status,
        extracted_text=res.extracted_text,
        error=res.error,
        metadata={"structured_result": structured_result.model_dump()}
    )
