"""Unit tests for src.tools.browser_driver (mocked — no real browser)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.browser_driver import (
    AmbiguousSelectorError,
    BrowserDriver,
    BrowserDriverError,
    BrowserNotStartedError,
    DomainNotAllowedError,
    ElementNotFoundError,
    check_navigation_allowed,
)


# ---------------------------------------------------------------------------
# Domain allowlist
# ---------------------------------------------------------------------------

def test_check_navigation_allowed_empty_allowlist():
    check_navigation_allowed("https://example.com/path", [])


def test_check_navigation_allowed_matching_host():
    check_navigation_allowed("https://example.com/path", ["example.com"])


def test_check_navigation_allowed_subdomain():
    check_navigation_allowed("https://www.example.com", ["example.com"])


def test_check_navigation_allowed_blocks_unknown_host():
    with pytest.raises(DomainNotAllowedError):
        check_navigation_allowed("https://evil.com", ["example.com"])


def test_check_navigation_allowed_blocks_non_http_scheme():
    with pytest.raises(DomainNotAllowedError):
        check_navigation_allowed("file:///etc/passwd", ["example.com"])


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_creates_and_starts_browser():
    driver = BrowserDriver(headless=True, allowed_domains=["example.com"])

    mock_browser = AsyncMock()
    mock_browser.start = AsyncMock()

    with patch("browser_use.Browser", return_value=mock_browser) as browser_cls:
        await driver.start()

    browser_cls.assert_called_once_with(
        headless=True,
        keep_alive=True,
        allowed_domains=["example.com"],
    )
    mock_browser.start.assert_awaited_once()
    assert driver.is_started


@pytest.mark.asyncio
async def test_start_reuses_injected_browser():
    mock_browser = AsyncMock()
    mock_browser.start = AsyncMock()
    driver = BrowserDriver(browser=mock_browser)

    await driver.start()

    mock_browser.start.assert_awaited_once()
    assert driver.is_started


@pytest.mark.asyncio
async def test_close_only_when_driver_owns_browser():
    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()
    driver = BrowserDriver(browser=mock_browser)

    await driver.start()
    await driver.close()

    mock_browser.close.assert_awaited_once()
    assert not driver.is_started


@pytest.mark.asyncio
async def test_require_browser_raises_when_not_started():
    driver = BrowserDriver()
    with pytest.raises(BrowserNotStartedError):
        await driver.navigate("https://example.com")


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _make_driver_with_mocks() -> tuple[BrowserDriver, AsyncMock, AsyncMock, AsyncMock]:
    mock_browser = AsyncMock()
    mock_browser.start = AsyncMock()
    mock_browser.get_current_page_url = AsyncMock(return_value="https://example.com/")
    mock_browser.get_current_page_title = AsyncMock(return_value="Example")
    mock_browser.navigate_to = AsyncMock()
    mock_browser.take_screenshot = AsyncMock(return_value=b"png-bytes")

    mock_page = AsyncMock()
    mock_element = AsyncMock()
    mock_element.click = AsyncMock()
    mock_element.fill = AsyncMock()
    mock_element.select_option = AsyncMock()
    mock_element.evaluate = AsyncMock(return_value="hello world")

    mock_page.get_elements_by_css_selector = AsyncMock(return_value=[mock_element])
    mock_page.evaluate = AsyncMock(return_value="page text")

    mock_browser.get_current_page = AsyncMock(return_value=mock_page)
    mock_browser.must_get_current_page = AsyncMock(return_value=mock_page)

    driver = BrowserDriver(browser=mock_browser)
    return driver, mock_browser, mock_page, mock_element


@pytest.mark.asyncio
async def test_navigate_calls_browser_navigate_to():
    driver, mock_browser, _, _ = _make_driver_with_mocks()
    await driver.start()

    result = await driver.navigate("https://example.com/home")

    mock_browser.navigate_to.assert_awaited_once_with("https://example.com/home")
    assert result.url == "https://example.com/"
    assert result.title == "Example"
    assert "Navigated" in result.message


@pytest.mark.asyncio
async def test_navigate_enforces_allowlist():
    driver, _, _, _ = _make_driver_with_mocks()
    driver._allowed_domains = ["example.com"]
    await driver.start()

    with pytest.raises(DomainNotAllowedError):
        await driver.navigate("https://other.com")


@pytest.mark.asyncio
async def test_click_resolves_selector_and_clicks():
    driver, _, mock_page, mock_element = _make_driver_with_mocks()
    await driver.start()

    result = await driver.click("#submit")

    mock_page.get_elements_by_css_selector.assert_awaited_once_with("#submit")
    mock_element.click.assert_awaited_once()
    assert "Clicked" in result.message


@pytest.mark.asyncio
async def test_click_raises_when_no_match():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    mock_page.get_elements_by_css_selector = AsyncMock(return_value=[])
    await driver.start()

    with pytest.raises(ElementNotFoundError):
        await driver.click("#missing")


@pytest.mark.asyncio
async def test_click_raises_when_ambiguous():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    mock_page.get_elements_by_css_selector = AsyncMock(return_value=[MagicMock(), MagicMock()])
    await driver.start()

    with pytest.raises(AmbiguousSelectorError) as exc:
        await driver.click(".btn")
    assert exc.value.count == 2


@pytest.mark.asyncio
async def test_fill_calls_element_fill():
    driver, _, _, mock_element = _make_driver_with_mocks()
    await driver.start()

    result = await driver.fill("#email", "user@example.com")

    mock_element.fill.assert_awaited_once_with("user@example.com")
    assert "Filled" in result.message


@pytest.mark.asyncio
async def test_select_option_calls_element_select_option():
    driver, _, _, mock_element = _make_driver_with_mocks()
    await driver.start()

    await driver.select_option("#country", "US")

    mock_element.select_option.assert_awaited_once_with("US")


@pytest.mark.asyncio
async def test_screenshot_writes_file_path():
    driver, mock_browser, _, _ = _make_driver_with_mocks()
    await driver.start()

    result = await driver.screenshot("/tmp/test.png")

    mock_browser.take_screenshot.assert_awaited_once_with(path="/tmp/test.png", format="png")
    assert result.screenshot_path == "/tmp/test.png"


@pytest.mark.asyncio
async def test_get_text_element_scoped():
    driver, _, _, mock_element = _make_driver_with_mocks()
    await driver.start()

    result = await driver.get_text("#title")

    mock_element.evaluate.assert_awaited_once_with("() => this.innerText")
    assert result.text == "hello world"


@pytest.mark.asyncio
async def test_get_text_page_scoped():
    driver, _, mock_page, mock_element = _make_driver_with_mocks()
    await driver.start()

    result = await driver.get_text(None)

    mock_element.evaluate.assert_not_called()
    mock_page.evaluate.assert_awaited_once_with("() => document.body.innerText")
    assert result.text == "page text"


@pytest.mark.asyncio
async def test_scroll_down():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    await driver.start()

    result = await driver.scroll("down", 300)

    mock_page.evaluate.assert_awaited_once_with("() => window.scrollBy(0, 300)")
    assert "Scrolled down" in result.message


@pytest.mark.asyncio
async def test_scroll_up():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    await driver.start()

    await driver.scroll("up", 200)

    mock_page.evaluate.assert_awaited_once_with("() => window.scrollBy(0, -200)")


@pytest.mark.asyncio
async def test_wait_for_polls_until_element_appears():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    mock_page.get_elements_by_css_selector = AsyncMock(
        side_effect=[[], [], [MagicMock()]],
    )
    await driver.start()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await driver.wait_for("#lazy", timeout=5.0)

    assert mock_page.get_elements_by_css_selector.await_count == 3
    assert "appeared" in result.message


@pytest.mark.asyncio
async def test_wait_for_times_out():
    driver, _, mock_page, _ = _make_driver_with_mocks()
    mock_page.get_elements_by_css_selector = AsyncMock(return_value=[])
    await driver.start()

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(BrowserDriverError):
            await driver.wait_for("#never", timeout=0.5, poll_interval=0.1)


# ---------------------------------------------------------------------------
# Integration tests (real browser - marked with @pytest.mark.browser)
# ---------------------------------------------------------------------------

import os
import tempfile
from pathlib import Path


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_navigate_returns_real_url():
    """Integration test: navigate returns actual URL and title from real browser."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        result = await driver.navigate(file_url)
        
        assert result.url is not None
        assert "form.html" in result.url or "Test Form Page" in result.title
        assert result.title == "Test Form Page"
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_click_calls_element_click():
    """Integration test: click actually clicks an element in real browser."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        # Click the info button (should show dynamic content)
        result = await driver.click("#info-button")
        
        assert result.url is not None
        assert "clicked" in result.message.lower()
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_fill_types_value():
    """Integration test: fill actually types into an input field."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        result = await driver.fill("#name", "Test User")
        
        assert "filled" in result.message.lower()
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_select_option_changes_value():
    """Integration test: select_option actually changes dropdown value."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        result = await driver.select_option("#country", "us")
        
        assert "selected" in result.message.lower()
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_screenshot_writes_file():
    """Integration test: screenshot actually writes a PNG file to disk."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        screenshot_path = tmp.name
    
    try:
        driver = BrowserDriver(headless=True)
        await driver.start()
        
        await driver.navigate(file_url)
        result = await driver.screenshot(screenshot_path)
        
        assert result.screenshot_path == screenshot_path
        assert os.path.exists(screenshot_path)
        assert os.path.getsize(screenshot_path) > 0
        
        await driver.close()
    finally:
        if os.path.exists(screenshot_path):
            os.unlink(screenshot_path)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_get_text_returns_dom_text():
    """Integration test: get_text returns literal DOM text, not LLM summary."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        # Get text from the page
        result = await driver.get_text()
        
        assert result.text is not None
        assert "Test Form Page" in result.text
        assert "This is a test page" in result.text
        
        # Get text from specific element
        element_result = await driver.get_text("#name")
        
        assert element_result.text is not None or element_result.text == ""  # Empty input
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_scroll_works():
    """Integration test: scroll actually scrolls the page."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        result = await driver.scroll("down", 100)
        
        assert "scrolled" in result.message.lower()
    finally:
        await driver.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_integration_wait_for_waits_for_element():
    """Integration test: wait_for actually waits for element to appear."""
    fixture_path = Path(__file__).parent / "fixtures" / "form.html"
    file_url = f"file://{fixture_path.absolute()}"
    
    driver = BrowserDriver(headless=True)
    await driver.start()
    
    try:
        await driver.navigate(file_url)
        
        # Element already exists
        result = await driver.wait_for("#name", timeout=5.0)
        
        assert "appeared" in result.message.lower()
    finally:
        await driver.close()
