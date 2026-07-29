import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from src.tools.browser_tool import ActionStatus
from src.agents.plan_execute.browser_pipelines.comparison import run_comparison_pipeline

@pytest.mark.asyncio
@patch('src.agents.plan_execute.browser_pipelines.comparison.asyncio.gather', new_callable=AsyncMock)
@patch('src.agents.plan_execute.browser_pipelines.comparison._extract_compare_tab')
async def test_run_comparison_pipeline(mock_extract, mock_gather):
    mock_browser = AsyncMock()
    mock_browser._ensure_browser = AsyncMock()
    # It's a synchronous function in BrowserTool, but it's mocked as AsyncMock. We'll leave it or mock it properly
    mock_browser._ensure_llm = MagicMock()
    
    mock_gather.return_value = [
        {"url": "http://site1.com", "data": {"price": "$100", "duration": "2h"}},
        {"url": "http://site2.com", "data": {"price": "$120", "duration": "1h 50m"}}
    ]
    
    result = await run_comparison_pipeline(mock_browser, "compare these", ["http://site1.com", "http://site2.com"], "price, duration")
    
    assert result.success is True
    assert "site1.com" in result.extracted_text
    assert "$100" in result.extracted_text
    assert "duration" in result.extracted_text
