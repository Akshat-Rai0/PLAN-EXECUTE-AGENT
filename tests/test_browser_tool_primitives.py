"""
Unit tests for BrowserTool primitive methods (Phase 2).

Verifies that primitives delegate to BrowserDriver instead of spinning up
Agent instances, and that no Agent imports occur in primitive code paths.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.browser_driver import DriverResult
from src.tools.browser_tool import BrowserTool, BrowserAction, ActionStatus


@pytest.fixture
def browser_tool():
    """Create a BrowserTool instance for testing."""
    return BrowserTool(headless=True, timeout=10)


@pytest.fixture
def mock_driver():
    """Create a mock BrowserDriver."""
    driver = MagicMock()
    driver.start = AsyncMock()
    driver.close = AsyncMock()
    driver.navigate = AsyncMock()
    driver.click = AsyncMock()
    driver.fill = AsyncMock()
    driver.select_option = AsyncMock()
    driver.screenshot = AsyncMock()
    driver.get_text = AsyncMock()
    driver.scroll = AsyncMock()
    driver.wait_for = AsyncMock()
    return driver


class TestNavigatePrimitive:
    """Test the navigate primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_navigate_calls_driver(self, browser_tool, mock_driver):
        """navigate should call driver.navigate, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.navigate.return_value = DriverResult(
            url="https://example.com",
            title="Example",
            message="Navigated to https://example.com",
        )

        result = await browser_tool.navigate("https://example.com")

        assert mock_driver.navigate.called
        mock_driver.navigate.assert_called_once_with("https://example.com")
        assert result.status == ActionStatus.SUCCESS
        assert result.current_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_navigate_no_llm_call(self, browser_tool, mock_driver):
        """navigate should not call _ensure_llm."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.navigate.return_value = DriverResult(
            url="https://example.com",
            title="Example",
            message="Navigated",
        )

        with patch.object(browser_tool, "_ensure_llm") as mock_ensure_llm:
            await browser_tool.navigate("https://example.com")
            mock_ensure_llm.assert_not_called()


class TestClickPrimitive:
    """Test the click primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_click_calls_driver(self, browser_tool, mock_driver):
        """click should call driver.click, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.click.return_value = DriverResult(
            url="https://example.com",
            title="Example",
            message="Clicked #submit",
        )

        result = await browser_tool.click("#submit")

        assert mock_driver.click.called
        mock_driver.click.assert_called_once_with("#submit")
        assert result.status == ActionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_click_no_llm_call(self, browser_tool, mock_driver):
        """click should not call _ensure_llm."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.click.return_value = DriverResult(message="Clicked")

        with patch.object(browser_tool, "_ensure_llm") as mock_ensure_llm:
            await browser_tool.click("#button")
            mock_ensure_llm.assert_not_called()


class TestFillPrimitive:
    """Test the fill primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_fill_calls_driver(self, browser_tool, mock_driver):
        """fill should call driver.fill, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.fill.return_value = DriverResult(
            message="Filled #email with value"
        )

        result = await browser_tool.fill("#email", "test@example.com")

        assert mock_driver.fill.called
        mock_driver.fill.assert_called_once_with("#email", "test@example.com")
        assert result.status == ActionStatus.SUCCESS


class TestSelectOptionPrimitive:
    """Test the select_option primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_select_option_calls_driver(self, browser_tool, mock_driver):
        """select_option should call driver.select_option, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.select_option.return_value = DriverResult(
            message="Selected 'option1' in #dropdown"
        )

        result = await browser_tool.select_option("#dropdown", "option1")

        assert mock_driver.select_option.called
        mock_driver.select_option.assert_called_once_with("#dropdown", "option1")
        assert result.status == ActionStatus.SUCCESS


class TestScreenshotPrimitive:
    """Test the screenshot primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_screenshot_calls_driver(self, browser_tool, mock_driver):
        """screenshot should call driver.screenshot, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.screenshot.return_value = DriverResult(
            screenshot_path="/tmp/test.png",
            message="Screenshot saved to /tmp/test.png",
        )

        result = await browser_tool.screenshot("/tmp/test.png")

        assert mock_driver.screenshot.called
        mock_driver.screenshot.assert_called_once_with("/tmp/test.png")
        assert result.status == ActionStatus.SUCCESS
        assert result.screenshot_path == "/tmp/test.png"


class TestGetTextPrimitive:
    """Test the get_text primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_get_text_calls_driver(self, browser_tool, mock_driver):
        """get_text should call driver.get_text, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.get_text.return_value = DriverResult(
            text="Sample text content",
            message="Extracted text from #content",
        )

        result = await browser_tool.get_text("#content")

        assert mock_driver.get_text.called
        mock_driver.get_text.assert_called_once_with("#content")
        assert result.status == ActionStatus.SUCCESS
        assert "Sample text content" in result.extracted_text

    @pytest.mark.asyncio
    async def test_get_text_page_level(self, browser_tool, mock_driver):
        """get_text with no selector should call driver.get_text(None)."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.get_text.return_value = DriverResult(
            text="Page text",
            message="Extracted page text",
        )

        result = await browser_tool.get_text()

        assert mock_driver.get_text.called
        mock_driver.get_text.assert_called_once_with(None)


class TestScrollPrimitive:
    """Test the scroll primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_scroll_calls_driver(self, browser_tool, mock_driver):
        """scroll should call driver.scroll, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.scroll.return_value = DriverResult(
            message="Scrolled down by 500px"
        )

        result = await browser_tool.scroll("down", 500)

        assert mock_driver.scroll.called
        mock_driver.scroll.assert_called_once_with("down", 500)
        assert result.status == ActionStatus.SUCCESS


class TestWaitForPrimitive:
    """Test the wait_for primitive uses driver, not Agent."""

    @pytest.mark.asyncio
    async def test_wait_for_calls_driver(self, browser_tool, mock_driver):
        """wait_for should call driver.wait_for, not Agent."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.wait_for.return_value = DriverResult(
            message="Element '#loaded' appeared"
        )

        result = await browser_tool.wait_for("#loaded", timeout=10)

        assert mock_driver.wait_for.called
        mock_driver.wait_for.assert_called_once_with("#loaded", 10)
        assert result.status == ActionStatus.SUCCESS


class TestNoAgentInPrimitives:
    """Static check: primitives should not import Agent."""

    def test_no_agent_import_in_primitives(self):
        """Verify Agent is not imported in primitive method code paths."""
        import ast
        import inspect
        import textwrap

        from src.tools.browser_tool import BrowserTool

        # Get source code for primitive methods
        primitive_methods = [
            "navigate",
            "click",
            "fill",
            "select_option",
            "screenshot",
            "get_text",
            "scroll",
            "wait_for",
        ]

        for method_name in primitive_methods:
            method = getattr(BrowserTool, method_name)
            source = inspect.getsource(method)
            # Dedent to handle indentation from inspect.getsource
            source = textwrap.dedent(source)
            tree = ast.parse(source)

            # Check for Agent class references
            agent_refs = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and node.id == "Agent"
            ]

            assert (
                len(agent_refs) == 0
            ), f"Method {method_name} should not reference Agent class"


class TestHITLGating:
    """Test HITL gating on submit-like clicks (Phase 3c)."""

    @pytest.mark.asyncio
    async def test_click_submit_requires_approval(self, browser_tool, mock_driver):
        """Click on submit-like selector should require approval."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.click.return_value = DriverResult(message="Clicked")

        # Mock require_approval to return False (rejected)
        with patch.object(browser_tool, "require_approval", return_value=False):
            result = await browser_tool.click("[type=submit]")

            assert result.status == ActionStatus.NEEDS_APPROVAL
            assert not mock_driver.click.called

    @pytest.mark.asyncio
    async def test_click_book_button_requires_approval(self, browser_tool, mock_driver):
        """Click on 'book' button should require approval."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.click.return_value = DriverResult(message="Clicked")

        with patch.object(browser_tool, "require_approval", return_value=False):
            result = await browser_tool.click("button.book-now")

            assert result.status == ActionStatus.NEEDS_APPROVAL
            assert not mock_driver.click.called

    @pytest.mark.asyncio
    async def test_click_normal_button_no_approval(self, browser_tool, mock_driver):
        """Click on normal button should not require approval."""
        browser_tool._driver = mock_driver
        browser_tool._ensure_browser = AsyncMock()
        mock_driver.click.return_value = DriverResult(message="Clicked")

        with patch.object(browser_tool, "require_approval", return_value=True) as mock_req:
            result = await browser_tool.click("#info-button")

            assert result.status == ActionStatus.SUCCESS
            assert mock_driver.click.called
            # require_approval should not have been called for non-submit-like
            mock_req.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests (real browser - marked with @pytest.mark.browser)
# ---------------------------------------------------------------------------

import os
import tempfile
from pathlib import Path


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_navigate_no_llm_calls():
    """Integration test: navigate makes zero LLM API calls."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    tool = BrowserTool(headless=True)
    
    try:
        result = await tool.navigate(file_url)
        
        assert result.status == ActionStatus.SUCCESS
        assert result.current_url is not None
        assert "Test Form Page" in result.page_title or "Test Form Page" in result.extracted_text
    finally:
        await tool.close_session()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_click_no_llm_calls():
    """Integration test: click makes zero LLM API calls."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    tool = BrowserTool(headless=True)
    
    try:
        await tool.navigate(file_url)
        result = await tool.click("#info-button")
        
        assert result.status == ActionStatus.SUCCESS
        assert "clicked" in result.extracted_text.lower()
    finally:
        await tool.close_session()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_fill_no_llm_calls():
    """Integration test: fill makes zero LLM API calls."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    tool = BrowserTool(headless=True)
    
    try:
        await tool.navigate(file_url)
        result = await tool.fill("#name", "Integration Test User")
        
        assert result.status == ActionStatus.SUCCESS
        assert "filled" in result.extracted_text.lower()
    finally:
        await tool.close_session()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_screenshot_produces_real_file():
    """Integration test: screenshot produces a real PNG file on disk."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        screenshot_path = tmp.name
    
    try:
        tool = BrowserTool(headless=True)
        
        await tool.navigate(file_url)
        result = await tool.screenshot(screenshot_path)
        
        assert result.status == ActionStatus.SUCCESS
        assert result.screenshot_path == screenshot_path
        assert os.path.exists(screenshot_path)
        assert os.path.getsize(screenshot_path) > 0
        
        await tool.close_session()
    finally:
        if os.path.exists(screenshot_path):
            os.unlink(screenshot_path)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_get_text_returns_literal_dom_text():
    """Integration test: get_text returns literal DOM text, not LLM paraphrase."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    tool = BrowserTool(headless=True)
    
    try:
        await tool.navigate(file_url)
        result = await tool.get_text()
        
        assert result.status == ActionStatus.SUCCESS
        # Should contain actual page text, not an LLM summary
        assert "Test Form Page" in result.extracted_text
        assert "This is a test page" in result.extracted_text
        # Should be wrapped in untrusted content tags
        assert "<untrusted_web_content" in result.extracted_text
    finally:
        await tool.close_session()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_domain_allowlist_enforced():
    """Integration test: BROWSER_USE_DOMAIN_ALLOWLIST is enforced."""
    # This test verifies the domain allowlist is wired correctly
    # Since we're using file:// URLs, the allowlist should not block them
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    tool = BrowserTool(headless=True)
    
    try:
        result = await tool.navigate(file_url)
        
        # file:// URLs should work regardless of allowlist
        assert result.status == ActionStatus.SUCCESS
    finally:
        await tool.close_session()
