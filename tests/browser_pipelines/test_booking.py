import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.browser_tool import ActionStatus
from src.agents.plan_execute.browser_pipelines.booking import run_booking_pipeline

@pytest.mark.asyncio
@patch('src.agents.plan_execute.browser_pipelines.booking.gather_options')
@patch('src.agents.plan_execute.browser_pipelines.booking.get_llm')
@patch('src.agents.plan_execute.browser_pipelines.booking.run_form_filling_pipeline')
async def test_run_booking_pipeline(mock_form, mock_llm, mock_gather):
    mock_browser = AsyncMock()
    
    mock_gather.return_value = [{"flight": "1A", "price": "$100"}]
    
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value.content = "I recommend flight 1A"
    mock_llm.return_value = mock_llm_instance
    
    # Task implies booking
    mock_form_result = AsyncMock()
    mock_form_result.success = True
    mock_form_result.extracted_text = "Booking successful"
    mock_form_result.status = ActionStatus.SUCCESS
    mock_form.return_value = mock_form_result
    
    result = await run_booking_pipeline(mock_browser, "book a flight", ["http://flights.com"])
    
    assert mock_form.called
    assert "Recommendation" in result.extracted_text
    assert "Booking successful" in result.extracted_text
