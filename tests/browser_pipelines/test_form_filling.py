import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.browser_tool import BrowserToolResult, ActionStatus
from src.agents.plan_execute.browser_pipelines.form_filling import run_form_filling_pipeline

@pytest.fixture
def mock_browser_tool():
    tool = AsyncMock()
    tool.run_task = AsyncMock()
    tool.fill = AsyncMock()
    tool.select_option = AsyncMock()
    tool.click = AsyncMock()
    return tool

@pytest.mark.asyncio
@patch('src.agents.plan_execute.browser_pipelines.form_filling.get_llm')
async def test_run_form_filling_pipeline(mock_get_llm, mock_browser_tool):
    # Mock identify_fields
    mock_browser_tool.run_task.side_effect = [
        BrowserToolResult(success=True, status=ActionStatus.SUCCESS, extracted_text='[{"name": "First Name", "type": "text", "selector": "#fname"}]'),
        BrowserToolResult(success=True, status=ActionStatus.SUCCESS, extracted_text='{"selector": "#submit-btn"}')
    ]
    
    # Mock resolve_field_values
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value.content = '[{"selector": "#fname", "action": "fill", "value": "John"}]'
    mock_get_llm.return_value = mock_llm_instance
    
    mock_browser_tool.fill.return_value = BrowserToolResult(success=True, status=ActionStatus.SUCCESS)
    mock_browser_tool.click.return_value = BrowserToolResult(success=True, status=ActionStatus.SUCCESS, extracted_text="Submitted")
    
    result = await run_form_filling_pipeline(mock_browser_tool, "My name is John")
    
    assert result.success is True
    assert result.extracted_text == "Submitted"
    
    # Verify calls
    assert mock_browser_tool.run_task.call_count == 2
    mock_browser_tool.fill.assert_called_once_with("#fname", "John")
    mock_browser_tool.click.assert_called_once_with("#submit-btn")
