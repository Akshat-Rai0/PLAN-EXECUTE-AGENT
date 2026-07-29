import pytest
from unittest.mock import patch, AsyncMock
import json

from src.tools.browser_tool import ActionStatus
from src.agents.plan_execute.browser_pipelines.data_collection import run_data_collection_pipeline

@pytest.mark.asyncio
@patch('src.agents.plan_execute.browser_pipelines.data_collection.BrowserTool')
async def test_run_data_collection_pipeline(mock_browser_tool_class):
    mock_instance = AsyncMock()
    mock_browser_tool_class.return_value = mock_instance
    
    mock_instance.run_task.return_value = AsyncMock(
        success=True,
        extracted_text='{"title": "Test Item", "price": "$10"}'
    )
    mock_instance.run_task.return_value.success = True
    mock_instance.run_task.return_value.extracted_text = '{"title": "Test Item", "price": "$10"}'
    
    # We supply a direct URL in targets to bypass TRUSTED_SOURCES for the test
    result = await run_data_collection_pipeline("Scrape this", ["http://example.com"], "price and title")
    
    assert result.success is True
    assert result.status == ActionStatus.SUCCESS
    
    data = json.loads(result.extracted_text)
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "http://example.com"
    assert data["results"][0]["data"]["title"] == "Test Item"
