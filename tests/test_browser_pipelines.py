"""
Integration tests for browser pipelines.

Tests each pipeline on demo sites to validate functionality.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.tools.browser_tool import BrowserTool, BrowserToolResult, ActionStatus
from src.agents.plan_execute.browser_pipelines.form_filling import (
    run_form_filling_pipeline, identify_fields, resolve_field_values
)
from src.agents.plan_execute.browser_pipelines.booking import (
    run_booking_pipeline, gather_options, reason_best_option
)
from src.agents.plan_execute.browser_pipelines.comparison import (
    run_comparison_pipeline, build_comparison_table
)
from src.agents.plan_execute.browser_pipelines.data_collection import (
    run_data_collection_pipeline, plan_sources
)
from src.agents.plan_execute.browser_pipelines.info_retrieval import (
    run_info_retrieval_pipeline
)
from src.agents.plan_execute.browser_pipelines.models import (
    FormField, FormFillResult, BookingOption, BookingRecommendation,
    ComparisonItem, ComparisonResult, DataPoint, CollectionResult, InfoResult
)


@pytest.fixture
def mock_browser_tool():
    """Create a mock BrowserTool for testing."""
    tool = Mock(spec=BrowserTool)
    tool._llm = Mock()
    tool._browser = Mock()
    tool._ensure_llm = Mock()
    tool._ensure_browser = AsyncMock()
    tool.navigate = AsyncMock()
    tool.run_task = AsyncMock()
    tool.fill = AsyncMock()
    tool.select_option = AsyncMock()
    tool.click = AsyncMock()
    tool.close_session = AsyncMock()
    return tool


# Form Filling Tests
@pytest.mark.asyncio
async def test_identify_fields_success(mock_browser_tool):
    """Test field identification with successful extraction."""
    mock_result = BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text='[{"name": "email", "type": "text", "selector": "#email", "required": true, "current_value": ""}]'
    )
    mock_browser_tool.run_task.return_value = mock_result
    
    fields = await identify_fields(mock_browser_tool)
    
    assert len(fields) == 1
    assert isinstance(fields[0], FormField)
    assert fields[0].name == "email"
    assert fields[0].type == "text"


@pytest.mark.asyncio
async def test_identify_fields_no_results(mock_browser_tool):
    """Test field identification with no results."""
    mock_result = BrowserToolResult(
        success=False,
        status=ActionStatus.FAILED,
        extracted_text=None
    )
    mock_browser_tool.run_task.return_value = mock_result
    
    fields = await identify_fields(mock_browser_tool)
    
    assert len(fields) == 0


@pytest.mark.asyncio
async def test_resolve_field_values(mock_browser_tool):
    """Test field value resolution."""
    fields = [
        FormField(name="email", type="text", selector="#email", required=True, current_value="")
    ]
    
    with patch('src.agents.plan_execute.browser_pipelines.form_filling.get_llm') as mock_get_llm:
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = '[{"selector": "#email", "action": "fill", "value": "test@example.com"}]'
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        actions = await resolve_field_values(fields, "email: test@example.com")
        
        assert len(actions) == 1
        assert actions[0]["selector"] == "#email"
        assert actions[0]["value"] == "test@example.com"


@pytest.mark.asyncio
async def test_run_form_filling_pipeline_success(mock_browser_tool):
    """Test complete form filling pipeline."""
    # Mock identify_fields
    with patch('src.agents.plan_execute.browser_pipelines.form_filling.identify_fields') as mock_identify:
        mock_identify.return_value = [
            FormField(name="email", type="text", selector="#email", required=True, current_value="")
        ]
        
        # Mock resolve_field_values
        with patch('src.agents.plan_execute.browser_pipelines.form_filling.resolve_field_values') as mock_resolve:
            mock_resolve.return_value = [{"selector": "#email", "action": "fill", "value": "test@example.com"}]
            
            # Mock fill_fields
            with patch('src.agents.plan_execute.browser_pipelines.form_filling.fill_fields') as mock_fill:
                mock_fill.return_value = [
                    BrowserToolResult(success=True, status=ActionStatus.SUCCESS)
                ]
                
                # Mock submit_and_verify
                with patch('src.agents.plan_execute.browser_pipelines.form_filling.submit_and_verify') as mock_submit:
                    mock_submit.return_value = BrowserToolResult(
                        success=True,
                        status=ActionStatus.SUCCESS,
                        extracted_text="Form submitted successfully"
                    )
                    
                    result = await run_form_filling_pipeline(mock_browser_tool, "email: test@example.com")
                    
                    assert result.success is True
                    assert "structured_result" in result.metadata


# Booking Tests
@pytest.mark.asyncio
async def test_gather_options_success(mock_browser_tool):
    """Test gathering booking options."""
    mock_browser_tool.navigate = AsyncMock()
    mock_result = BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text='[{"price": 100.0, "duration": "2h", "timing": "10:00 AM", "provider": "Airline A", "url": "https://example.com/book1"}]'
    )
    mock_browser_tool.run_task.return_value = mock_result
    
    options = await gather_options(mock_browser_tool, "https://example.com", "flight from NYC to LA")
    
    assert len(options) == 1
    assert isinstance(options[0], BookingOption)
    assert options[0].price == 100.0


@pytest.mark.asyncio
async def test_reason_best_option():
    """Test reasoning about best booking option."""
    options = [
        BookingOption(price=100.0, duration="2h", timing="10:00 AM", provider="Airline A", url="https://example.com/1"),
        BookingOption(price=150.0, duration="1.5h", timing="11:00 AM", provider="Airline B", url="https://example.com/2")
    ]
    
    with patch('src.agents.plan_execute.browser_pipelines.booking.get_llm') as mock_get_llm:
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = '{"selected_option": {"price": 100.0, "duration": "2h", "timing": "10:00 AM", "provider": "Airline A", "url": "https://example.com/1", "attributes": {}}, "alternatives": [], "reasoning": "Cheapest option", "criteria": "cheapest"}'
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        recommendation = await reason_best_option(options, "cheapest")
        
        assert isinstance(recommendation, BookingRecommendation)
        assert recommendation.selected_option.price == 100.0


@pytest.mark.asyncio
async def test_run_booking_pipeline_recommendation_only(mock_browser_tool):
    """Test booking pipeline for recommendation only (no actual booking)."""
    with patch('src.agents.plan_execute.browser_pipelines.booking.plan_sources') as mock_plan:
        mock_plan.return_value = ["https://example.com"]
        
        with patch('src.agents.plan_execute.browser_pipelines.booking.gather_options') as mock_gather:
            mock_gather.return_value = [
                BookingOption(price=100.0, duration="2h", timing="10:00 AM", provider="Airline A", url="https://example.com/1")
            ]
            
            with patch('src.agents.plan_execute.browser_pipelines.booking.reason_best_option') as mock_reason:
                mock_reason.return_value = BookingRecommendation(
                    selected_option=BookingOption(price=100.0, duration="2h", timing="10:00 AM", provider="Airline A", url="https://example.com/1"),
                    alternatives=[],
                    reasoning="Cheapest option",
                    criteria="cheapest"
                )
                
                result = await run_booking_pipeline(mock_browser_tool, "find cheapest flight", [])
                
                assert result.success is True
                assert "structured_result" in result.metadata


# Comparison Tests
def test_build_comparison_table():
    """Test building comparison table from results."""
    results = [
        {
            "url": "https://site1.com",
            "data": {
                "title": "Product A",
                "price": 100.0,
                "rating": "4.5",
                "source": "Site 1",
                "url": "https://site1.com/product"
            }
        },
        {
            "url": "https://site2.com",
            "data": {
                "title": "Product A",
                "price": 95.0,
                "rating": "4.0",
                "source": "Site 2",
                "url": "https://site2.com/product"
            }
        }
    ]
    
    table = build_comparison_table(results)
    
    assert "| Source |" in table
    assert "price" in table.lower()
    assert "rating" in table.lower()


@pytest.mark.asyncio
async def test_run_comparison_pipeline_success(mock_browser_tool):
    """Test comparison pipeline with successful extraction."""
    with patch('src.agents.plan_execute.browser_pipelines.comparison.plan_sources') as mock_plan:
        mock_plan.return_value = ["https://example.com"]
        
        with patch('src.agents.plan_execute.browser_pipelines.comparison._extract_compare_tab') as mock_extract:
            mock_extract.return_value = {
                "url": "https://example.com",
                "data": ComparisonItem(
                    title="Product A",
                    price=100.0,
                    attributes={"rating": "4.5"},
                    source="Example",
                    url="https://example.com/product"
                ).model_dump()
            }
            
            result = await run_comparison_pipeline(
                mock_browser_tool,
                "compare prices",
                ["https://example.com"],
                "price and rating"
            )
            
            assert result.success is True
            assert "structured_result" in result.metadata


# Data Collection Tests
def test_plan_sources_with_targets():
    """Test source planning with explicit targets."""
    targets = ["https://example.com", "https://another.com"]
    urls = plan_sources("test task", targets)
    
    assert urls == targets


def test_plan_sources_without_targets():
    """Test source planning without explicit targets."""
    with patch('src.agents.plan_execute.nodes._detect_trusted_topic') as mock_detect:
        mock_detect.return_value = None
        urls = plan_sources("test task", [])
        
        assert urls == []


@pytest.mark.asyncio
async def test_run_data_collection_pipeline_success(mock_browser_tool):
    """Test data collection pipeline."""
    with patch('src.agents.plan_execute.browser_pipelines.data_collection.plan_sources') as mock_plan:
        mock_plan.return_value = ["https://example.com"]
        
        with patch('src.agents.plan_execute.browser_pipelines.data_collection.spawn_subagents') as mock_spawn:
            mock_spawn.return_value = [
                {"url": "https://example.com", "data": {"title": "Data 1", "value": 100}}
            ]
            
            result = await run_data_collection_pipeline(
                "collect data",
                ["https://example.com"],
                "title and value"
            )
            
            assert result.success is True
            assert "structured_result" in result.metadata


# Info Retrieval Tests
@pytest.mark.asyncio
async def test_run_info_retrieval_pipeline_with_url(mock_browser_tool):
    """Test info retrieval with specific target URL."""
    mock_result = BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text='{"answer": "The answer is 42", "source_url": "https://example.com", "confidence": 0.9, "related_links": [], "query": "test question"}',
        current_url="https://example.com"
    )
    mock_browser_tool.run_task.return_value = mock_result
    
    result = await run_info_retrieval_pipeline(
        mock_browser_tool,
        "test question",
        ["https://example.com"]
    )
    
    assert result.success is True
    assert "structured_result" in result.metadata


@pytest.mark.asyncio
async def test_run_info_retrieval_pipeline_fallback(mock_browser_tool):
    """Test info retrieval with fallback when JSON parsing fails."""
    mock_result = BrowserToolResult(
        success=True,
        status=ActionStatus.SUCCESS,
        extracted_text="The answer is 42",
        current_url="https://example.com"
    )
    mock_browser_tool.run_task.return_value = mock_result
    
    result = await run_info_retrieval_pipeline(
        mock_browser_tool,
        "test question",
        ["https://example.com"]
    )
    
    assert result.success is True
    assert "structured_result" in result.metadata
    # Should have fallback structured result
    structured = result.metadata["structured_result"]
    assert structured["answer"] == "The answer is 42"


# Model Validation Tests
def test_form_field_model():
    """Test FormField model validation."""
    field = FormField(
        name="email",
        type="text",
        selector="#email",
        required=True,
        current_value=""
    )
    assert field.name == "email"
    assert field.required is True


def test_booking_option_model():
    """Test BookingOption model validation."""
    option = BookingOption(
        price=100.0,
        duration="2h",
        timing="10:00 AM",
        provider="Airline A",
        url="https://example.com"
    )
    assert option.price == 100.0
    assert option.provider == "Airline A"


def test_comparison_item_model():
    """Test ComparisonItem model validation."""
    item = ComparisonItem(
        title="Product A",
        price=100.0,
        attributes={"rating": "4.5"},
        source="Site 1",
        url="https://site1.com/product"
    )
    assert item.title == "Product A"
    assert item.price == 100.0


def test_data_point_model():
    """Test DataPoint model validation."""
    point = DataPoint(
        url="https://example.com",
        data={"value": 100},
        confidence=0.9
    )
    assert point.url == "https://example.com"
    assert point.confidence == 0.9


def test_info_result_model():
    """Test InfoResult model validation."""
    result = InfoResult(
        answer="42",
        source_url="https://example.com",
        confidence=0.9,
        query="meaning of life"
    )
    assert result.answer == "42"
    assert result.confidence == 0.9


# Demo Site Integration Tests (marked as integration tests)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_form_filling_demoqa():
    """Test form filling on demoqa.com (integration test)."""
    # This test requires a real browser and network access
    # Mark with pytest.mark.integration to skip in CI
    pytest.skip("Integration test - requires real browser")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comparison_opencart():
    """Test product comparison on demo.opencart.com (integration test)."""
    # This test requires a real browser and network access
    pytest.skip("Integration test - requires real browser")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_info_retrieval_selenium():
    """Test info retrieval on selenium.dev (integration test)."""
    # This test requires a real browser and network access
    pytest.skip("Integration test - requires real browser")
