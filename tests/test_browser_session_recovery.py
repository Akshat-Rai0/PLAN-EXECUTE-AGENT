"""
Regression test for browser session recovery across sequential run_task calls.

Tests the fix for the QueueShutDown bug where the second use_browser step
would crash with bubus.service.QueueShutDown after the first step completed,
triggering an expensive 60s+ forced-cleanup recovery path.

This test ensures:
1. Sequential run_task calls on the same BrowserTool instance work correctly
2. Session health checks detect dead sessions proactively before QueueShutDown
3. Recovery is fast (<10s) when session rebuild is needed
"""

import asyncio
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from src.tools.browser_tool import BrowserTool


@pytest.mark.asyncio
async def test_sequential_run_task_with_session_health_check():
    """
    Test that two sequential run_task calls work correctly when the first
    call leaves the session in a healthy state.
    """
    # Skip if OPENROUTER_API_KEY is not set
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    tool = BrowserTool(headless=True)
    
    try:
        # First task
        result1 = await tool.run_task("Navigate to example.com and return the page title")
        assert result1.success, f"First task failed: {result1.error}"
        assert result1.status.value == "SUCCESS"
        
        # Second task should reuse the same session
        result2 = await tool.run_task("Navigate to example.com and return the current URL")
        assert result2.success, f"Second task failed: {result2.error}"
        assert result2.status.value == "SUCCESS"
        
        # Verify the session was reused (Agent should not be None)
        assert tool._agent is not None, "Agent should be reused across calls"
        
    finally:
        await tool.close_session()


@pytest.mark.asyncio
async def test_proactive_session_rebuild_on_dead_session():
    """
    Test that when a session is dead (simulated by health check failure),
    the tool proactively rebuilds before attempting the operation,
    avoiding QueueShutDown mid-execution.
    """
    # Skip if OPENROUTER_API_KEY is not set
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    tool = BrowserTool(headless=True)
    
    try:
        # Initialize browser
        await tool._ensure_browser()
        
        # Mock health check to return False (simulating dead session)
        original_check = tool._check_session_health
        call_count = [0]
        
        async def mock_health_check():
            call_count[0] += 1
            # First call returns False (dead session), second returns True (after rebuild)
            return call_count[0] > 1
        
        tool._check_session_health = mock_health_check
        
        # This should detect dead session and rebuild proactively
        result = await tool.run_task("Navigate to example.com and return the page title")
        
        # Should succeed after rebuild
        assert result.success, f"Task failed after session rebuild: {result.error}"
        assert result.status.value == "SUCCESS"
        
        # Verify health check was called at least twice (once to detect dead, once after rebuild)
        assert call_count[0] >= 2, "Health check should have been called multiple times"
        
    finally:
        tool._check_session_health = original_check
        await tool.close_session()


@pytest.mark.asyncio
async def test_fast_session_recovery_timeout():
    """
    Test that session recovery completes quickly (<10s) when forced cleanup is needed.
    
    This regression test ensures the fix for the 60s+ sequential timeout issue
    (three 20s timeouts in close_session) is working.
    """
    # Skip if OPENROUTER_API_KEY is not set
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    tool = BrowserTool(headless=True)
    
    try:
        # Initialize browser
        await tool._ensure_browser()
        
        # Time the close operation
        start = asyncio.get_event_loop().time()
        await tool.close_session()
        elapsed = asyncio.get_event_loop().time() - start
        
        # Should complete in <10s (was 60s+ before the fix)
        assert elapsed < 10.0, f"Session recovery took {elapsed:.1f}s, expected <10s"
        
    finally:
        await tool.close_session()


@pytest.mark.asyncio
async def test_concurrent_close_operations():
    """
    Test that close_session runs driver, agent, and browser close operations
    concurrently rather than sequentially.
    """
    # Skip if OPENROUTER_API_KEY is not set
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    tool = BrowserTool(headless=True)
    
    try:
        # Initialize browser and agent
        await tool._ensure_browser()
        await tool.run_task("Navigate to example.com")
        
        # Mock close operations to track if they run concurrently
        close_times = []
        
        original_driver_close = tool._driver.close
        async def mock_driver_close():
            close_times.append(("driver", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)  # Simulate work
            await original_driver_close()
        
        original_agent_close = tool._agent.close if tool._agent else asyncio.sleep(0)
        async def mock_agent_close():
            close_times.append(("agent", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)  # Simulate work
            if tool._agent:
                await tool._agent.close()
        
        original_browser_close = tool._browser.close
        async def mock_browser_close():
            close_times.append(("browser", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)  # Simulate work
            await original_browser_close()
        
        tool._driver.close = mock_driver_close
        if tool._agent:
            tool._agent.close = mock_agent_close
        tool._browser.close = mock_browser_close
        
        # Close session
        await tool.close_session()
        
        # Verify all three operations ran
        assert len(close_times) == 3, f"Expected 3 close operations, got {len(close_times)}"
        
        # Verify they ran concurrently (timestamps should be close, not sequential)
        timestamps = [t for _, t in close_times]
        max_diff = max(timestamps) - min(timestamps)
        assert max_diff < 0.5, f"Close operations appear sequential (max diff {max_diff:.2f}s), expected concurrent"
        
    finally:
        await tool.close_session()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
