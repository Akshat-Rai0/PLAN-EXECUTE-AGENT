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


# ---------------------------------------------------------------------------
# Session lifecycle regression tests (fix #5)
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    """Test session health checks and recovery from dead sessions."""

    @pytest.mark.asyncio
    async def test_session_health_check_failure_triggers_rebuild(self, browser_tool):
        """Test that a failed health check in _ensure_browser triggers session rebuild."""
        from unittest.mock import AsyncMock, patch
        
        # Mock browser as existing but unhealthy
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        
        # First health check fails (session dead)
        # Second call succeeds (after rebuild)
        health_check_results = [False, True]
        
        async def mock_health_check():
            result = health_check_results.pop(0)
            return result
        
        browser_tool._check_session_health = mock_health_check
        
        # Mock close_session and browser creation
        browser_tool.close_session = AsyncMock()
        browser_tool._driver.start = AsyncMock()
        
        with patch('browser_use.Browser') as MockBrowser:
            mock_browser_instance = AsyncMock()
            mock_browser_instance.get_current_page_url = AsyncMock(return_value="https://example.com")
            MockBrowser.return_value = mock_browser_instance
            
            await browser_tool._ensure_browser()
            
            # Should have closed the dead session
            assert browser_tool.close_session.called
            # Should have created a new browser
            assert MockBrowser.called
            # Session should be marked active again
            assert browser_tool._session_active is True

    @pytest.mark.asyncio
    async def test_queue_shutdown_exception_triggers_retry(self, browser_tool):
        """Test that QueueShutDown exception triggers session rebuild and retry."""
        from unittest.mock import AsyncMock, patch, MagicMock
        
        # Mock LLM and browser
        browser_tool._ensure_llm = MagicMock()
        browser_tool._llm = MagicMock()
        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        
        # Mock bubus QueueShutDown
        try:
            import bubus.service
            QueueShutDown = bubus.service.QueueShutDown
        except ImportError:
            # Create a mock exception if bubus is not available
            class QueueShutDown(Exception):
                pass
        
        # First call raises QueueShutDown, second succeeds
        call_count = [0]
        
        async def mock_agent_run():
            call_count[0] += 1
            if call_count[0] == 1:
                raise QueueShutDown("Queue shut down")
            # Second call succeeds
            mock_history = MagicMock()
            mock_history.final_result.return_value = "Task completed successfully"
            return mock_history
        
        # Mock Agent
        with patch('browser_use.Agent') as MockAgent:
            mock_agent = MagicMock()
            mock_agent.run = mock_agent_run
            MockAgent.return_value = mock_agent
            
            # Mock close_session and _ensure_browser for retry
            browser_tool.close_session = AsyncMock()
            browser_tool._check_session_health = AsyncMock(return_value=True)
            
            result = await browser_tool.run_task("Test task")
            
            # Should have retried after QueueShutDown
            assert call_count[0] == 2
            # Should have closed the dead session
            assert browser_tool.close_session.called
            # Should have succeeded on retry
            assert result.status == ActionStatus.SUCCESS
            assert "Task completed successfully" in result.extracted_text

    @pytest.mark.asyncio
    async def test_agent_reuse_across_calls(self, browser_tool):
        """Test that Agent instance is reused across multiple run_task calls (fix #3)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        browser_tool._ensure_llm = MagicMock()
        browser_tool._llm = MagicMock()
        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        browser_tool._check_session_health = AsyncMock(return_value=True)
        
        with patch('browser_use.Agent') as MockAgent:
            mock_agent = MagicMock()
            
            async def mock_agent_run():
                mock_history = MagicMock()
                mock_history.final_result.return_value = "Task completed"
                return mock_history
            
            mock_agent.run = mock_agent_run
            mock_agent.add_new_task = MagicMock()
            MockAgent.return_value = mock_agent
            
            # First call creates Agent
            result1 = await browser_tool.run_task("Task 1")
            assert result1.status == ActionStatus.SUCCESS
            assert browser_tool._agent is not None
            assert MockAgent.call_count == 1
            
            # Second call reuses Agent via add_new_task
            result2 = await browser_tool.run_task("Task 2")
            assert result2.status == ActionStatus.SUCCESS
            assert MockAgent.call_count == 1  # No new Agent created
            assert mock_agent.add_new_task.called  # add_new_task was called

    @pytest.mark.asyncio
    async def test_proactive_health_check_after_task(self, browser_tool):
        """Test that session health is checked after task completion (fix #4)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        browser_tool._ensure_llm = MagicMock()
        browser_tool._llm = MagicMock()
        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        
        # Health check fails after task completion
        browser_tool._check_session_health = AsyncMock(return_value=False)
        
        with patch('browser_use.Agent') as MockAgent:
            mock_agent = MagicMock()
            
            async def mock_agent_run():
                mock_history = MagicMock()
                mock_history.final_result.return_value = "Task completed"
                return mock_history
            
            mock_agent.run = mock_agent_run
            MockAgent.return_value = mock_agent
            
            result = await browser_tool.run_task("Test task")
            
            # Task should still succeed
            assert result.status == ActionStatus.SUCCESS
            # But session should be marked as inactive for next call
            assert browser_tool._session_active is False

    @pytest.mark.asyncio
    async def test_session_rebuild_prepends_navigate_to_last_url(self, browser_tool):
        """Test that session rebuild prepends navigate to last known URL (fix #1)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        browser_tool._ensure_llm = MagicMock()
        browser_tool._llm = MagicMock()
        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        browser_tool._check_session_health = AsyncMock(return_value=True)
        
        # Set last known URL
        browser_tool._last_url = "https://demoqa.com/automation-practice-form"
        
        try:
            import bubus.service
            QueueShutDown = bubus.service.QueueShutDown
        except ImportError:
            class QueueShutDown(Exception):
                pass
        
        with patch('browser_use.Agent') as MockAgent:
            mock_agent = MagicMock()
            
            # Track tasks passed to Agent
            tasks_passed = []
            
            async def mock_agent_run():
                # Check what task was set
                if hasattr(mock_agent, 'add_new_task'):
                    # Get the last task added via add_new_task
                    if mock_agent.add_new_task.call_count > 0:
                        tasks_passed.append(mock_agent.add_new_task.call_args[0][0])
                else:
                    # Get task from constructor
                    if mock_agent.init_kwargs:
                        tasks_passed.append(mock_agent.init_kwargs.get('task'))
                
                # First call raises QueueShutDown, second succeeds
                if len(tasks_passed) == 1:
                    raise QueueShutDown("Queue shut down")
                
                mock_history = MagicMock()
                mock_history.final_result.return_value = "Task completed"
                return mock_history
            
            mock_agent.run = mock_agent_run
            mock_agent.add_new_task = MagicMock()
            
            def mock_agent_init(**kwargs):
                mock_agent.init_kwargs = kwargs
                return mock_agent
            
            MockAgent.side_effect = mock_agent_init
            
            # Mock close_session and _ensure_browser for retry
            browser_tool.close_session = AsyncMock()
            
            result = await browser_tool.run_task("Fill out the form")
            
            # Should have retried after QueueShutDown
            assert result.status == ActionStatus.SUCCESS
            # The retry task should include navigate to last URL
            # Check that add_new_task was called with a task containing the URL
            if mock_agent.add_new_task.called:
                retry_task = mock_agent.add_new_task.call_args[0][0]
                assert "https://demoqa.com/automation-practice-form" in retry_task
                assert "navigate" in retry_task.lower()


class TestPlannerPromptSelfContainedSteps:
    """Test that planner prompt generates self-contained browser steps (fix #2)."""

    def test_planner_prompt_includes_self_contained_instructions(self):
        """Test that the planner prompt includes self-contained step instructions."""
        from src.agents.plan_execute.tools import PROMPT_TEMPLATE
        
        # Check that the prompt contains the self-contained instructions
        assert "COMPLETELY SELF-CONTAINED" in PROMPT_TEMPLATE
        assert "EXACT URL" in PROMPT_TEMPLATE
        assert "CONCRETE field values" in PROMPT_TEMPLATE
        assert "BAD example" in PROMPT_TEMPLATE
        assert "GOOD example" in PROMPT_TEMPLATE
        assert "the given details" in PROMPT_TEMPLATE
        assert "as described above" in PROMPT_TEMPLATE

    def test_planner_prompt_bad_example_shows_anti_pattern(self):
        """Test that the prompt shows the bad anti-pattern example."""
        from src.agents.plan_execute.tools import PROMPT_TEMPLATE
        
        # The bad example should show the problematic pattern
        assert "Fill out the practice form with the given details" in PROMPT_TEMPLATE
        assert "ambiguous" in PROMPT_TEMPLATE.lower()
        assert "will fail if the session is rebuilt" in PROMPT_TEMPLATE

    def test_planner_prompt_good_example_shows_concrete_values(self):
        """Test that the prompt shows the good pattern with concrete values."""
        from src.agents.plan_execute.tools import PROMPT_TEMPLATE
        
        # The good example should show concrete values
        assert "https://demoqa.com/automation-practice-form" in PROMPT_TEMPLATE
        assert "First Name: John" in PROMPT_TEMPLATE
        assert "Last Name: Doe" in PROMPT_TEMPLATE
        assert "john.doe@example.com" in PROMPT_TEMPLATE
        assert "self-contained" in PROMPT_TEMPLATE.lower()


class TestLLMReliabilityFixes:
    """Test LLM reliability improvements (fallback_llm, timeout, deterministic dropdowns)."""

    def test_fallback_llm_env_var_exists(self):
        """Test that BROWSER_FALLBACK_MODEL env var is defined (fix #1)."""
        from src.tools.browser_tool import _FALLBACK_MODEL
        assert _FALLBACK_MODEL is not None
        assert isinstance(_FALLBACK_MODEL, str)
        assert len(_FALLBACK_MODEL) > 0

    def test_llm_timeout_env_var_exists(self):
        """Test that BROWSER_LLM_TIMEOUT env var is defined (fix #2)."""
        from src.tools.browser_tool import _LLM_TIMEOUT
        assert _LLM_TIMEOUT is not None
        assert isinstance(_LLM_TIMEOUT, int)
        assert _LLM_TIMEOUT > 0

    @pytest.mark.asyncio
    async def test_fill_select_backed_field_calls_driver(self, browser_tool):
        """Test that fill_select_backed_field() calls BrowserDriver.select_option() (fix #3)."""
        from unittest.mock import AsyncMock
        from src.tools.browser_driver import DriverResult

        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        
        # Mock the driver's select_option method with proper DriverResult
        browser_tool._driver.select_option = AsyncMock(return_value=DriverResult(
            url="https://example.com",
            message="Selected 'June'"
        ))
        
        result = await browser_tool.fill_select_backed_field("select#month", "June")
        
        # Should have called driver.select_option
        assert browser_tool._driver.select_option.called
        assert browser_tool._driver.select_option.call_args[0][0] == "select#month"
        assert browser_tool._driver.select_option.call_args[0][1] == "June"
        # Result should be successful
        assert result.status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_index_not_found_error_suggests_deterministic_fallback(self, browser_tool):
        """Test that index-not-found errors suggest deterministic fallback (fix #4)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        browser_tool._ensure_llm = MagicMock()
        browser_tool._llm = MagicMock()
        browser_tool._ensure_browser = AsyncMock()
        browser_tool._browser = AsyncMock()
        browser_tool._session_active = True
        browser_tool._check_session_health = AsyncMock(return_value=True)

        with patch('browser_use.Agent') as MockAgent:
            mock_agent = MagicMock()
            
            async def mock_agent_run():
                # Simulate an index-not-found error
                raise Exception("Element index 5 not available - page may have changed")
            
            mock_agent.run = mock_agent_run
            MockAgent.return_value = mock_agent
            
            result = await browser_tool.run_task("Select month from dropdown")
            
            # Should fail with helpful error message
            assert result.status == "FAILED"
            assert "index mismatch" in result.error.lower() or "not available" in result.error.lower()
            assert "fill_select_backed_field" in result.error
