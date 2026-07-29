from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus

async def run_info_retrieval_pipeline(browser_tool: BrowserTool, task: str, targets: list[str]) -> BrowserToolResult:
    """End-to-end information retrieval pipeline.
    
    Simpler than data collection: single trusted-source lookup, single-page read, single-answer synthesis.
    """
    
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
        prompt = f"Using this page as a starting point, find the answer to the following question or task: {task}"
    else:
        # No specific source, let the agent decide how to retrieve the info
        prompt = f"Find the answer to the following question or task: {task}"
        
    return await browser_tool.run_task(task=prompt, max_steps=10)
