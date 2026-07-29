import pytest
from unittest.mock import AsyncMock

from src.tools.browser_tool import ActionStatus, BrowserToolResult
from src.agents.plan_execute.browser_pipelines.info_retrieval import run_info_retrieval_pipeline

@pytest.mark.asyncio
async def test_run_info_retrieval_pipeline():
    mock_browser = AsyncMock()
    mock_browser.run_task.return_value = BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text="The answer is 42."
    )
    
    result = await run_info_retrieval_pipeline(mock_browser, "What is the answer?", ["http://example.com"])
    
    assert result.success is True
    assert result.extracted_text == "The answer is 42."
    mock_browser.navigate.assert_called_once_with("http://example.com")
