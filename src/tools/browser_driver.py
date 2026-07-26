"""
Deterministic CDP/DOM browser driver.

Wraps browser_use's Browser / Page / Element APIs for primitive actions
(navigate, click, fill, …) without spinning up an LLM agent per call.

BrowserTool's high-level ``run_task`` path still uses browser_use.Agent;
this module is the Tier-1 driver layer only.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from browser_use import Browser
    from browser_use.actor.element import Element
    from browser_use.actor.page import Page


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class BrowserDriverError(Exception):
    """Base error for deterministic browser driver operations."""


class ElementNotFoundError(BrowserDriverError):
    """Raised when a CSS selector matches no elements."""

    def __init__(self, selector: str):
        self.selector = selector
        super().__init__(f"No element matched selector: {selector!r}")


class AmbiguousSelectorError(BrowserDriverError):
    """Raised when a CSS selector matches more than one element."""

    def __init__(self, selector: str, count: int):
        self.selector = selector
        self.count = count
        super().__init__(
            f"Selector {selector!r} matched {count} elements; expected exactly one"
        )


class DomainNotAllowedError(BrowserDriverError):
    """Raised when navigation targets a host outside the allowlist."""

    def __init__(self, url: str, allowed_domains: list[str]):
        self.url = url
        self.allowed_domains = allowed_domains
        super().__init__(
            f"Navigation to {url!r} blocked — host not in allowlist {allowed_domains!r}"
        )


class BrowserNotStartedError(BrowserDriverError):
    """Raised when an operation requires a live browser session."""


# ---------------------------------------------------------------------------
# Result payload (driver layer — mapped to BrowserToolResult upstream)
# ---------------------------------------------------------------------------

@dataclass
class DriverResult:
    """Structured outcome from a single deterministic browser action."""

    url: str | None = None
    title: str | None = None
    text: str | None = None
    screenshot_path: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _host_matches_allowlist(hostname: str, allowed_domains: list[str]) -> bool:
    hostname = hostname.lower().rstrip(".")
    for domain in allowed_domains:
        domain = domain.lower().lstrip(".")
        if hostname == domain or hostname.endswith(f".{domain}"):
            return True
    return False


def check_navigation_allowed(url: str, allowed_domains: list[str]) -> None:
    """Raise DomainNotAllowedError if *url* is outside *allowed_domains*."""
    if not allowed_domains:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise DomainNotAllowedError(url, allowed_domains)
    hostname = parsed.hostname
    if not hostname or not _host_matches_allowlist(hostname, allowed_domains):
        raise DomainNotAllowedError(url, allowed_domains)


class BrowserDriver:
    """
    Thin async wrapper over browser_use CDP primitives.

    One ``Browser`` session is created (or injected) and reused across calls.
    """

    def __init__(
        self,
        *,
        browser: Browser | None = None,
        headless: bool | None = None,
        allowed_domains: list[str] | None = None,
        sandbox_mode: bool = False,
    ):
        self._browser = browser
        self._owns_browser = browser is None
        self._headless = (
            headless
            if headless is not None
            else os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in ("1", "true", "yes")
        )
        self._allowed_domains = list(allowed_domains or [])
        self._sandbox_mode = sandbox_mode
        self._started = False

    @property
    def browser(self) -> Browser | None:
        return self._browser

    @property
    def is_started(self) -> bool:
        return self._started and self._browser is not None

    async def start(self) -> None:
        """Create and start the underlying browser session if needed."""
        if self._browser is not None and self._started:
            return

        if self._browser is None:
            from browser_use import Browser

            config: dict = {"headless": self._headless, "keep_alive": True}
            if self._sandbox_mode:
                config["headless"] = True
                config["disable_security"] = False
            if self._allowed_domains:
                config["allowed_domains"] = self._allowed_domains

            self._browser = Browser(**config)
            self._owns_browser = True

        await self._browser.start()
        self._started = True

    async def close(self) -> None:
        """Tear down the browser session when this driver owns it."""
        if self._browser is None:
            return
        try:
            await self._browser.close()
        finally:
            self._browser = None
            self._started = False

    async def current_url(self) -> str:
        browser = await self._require_browser()
        return await browser.get_current_page_url()

    async def current_title(self) -> str:
        browser = await self._require_browser()
        return await browser.get_current_page_title()

    async def navigate(self, url: str) -> DriverResult:
        check_navigation_allowed(url, self._allowed_domains)
        browser = await self._require_browser()
        await browser.navigate_to(url)
        title = await browser.get_current_page_title()
        current = await browser.get_current_page_url()
        return DriverResult(
            url=current,
            title=title,
            message=f"Navigated to {current}",
        )

    async def click(self, selector: str) -> DriverResult:
        element = await self._resolve_element(selector)
        await element.click()
        browser = await self._require_browser()
        return DriverResult(
            url=await browser.get_current_page_url(),
            title=await browser.get_current_page_title(),
            message=f"Clicked {selector!r}",
        )

    async def fill(self, selector: str, value: str) -> DriverResult:
        element = await self._resolve_element(selector)
        await element.fill(value)
        return DriverResult(message=f"Filled {selector!r}")

    async def select_option(self, selector: str, value: str) -> DriverResult:
        element = await self._resolve_element(selector)
        await element.select_option(value)
        return DriverResult(message=f"Selected {value!r} in {selector!r}")

    async def screenshot(self, save_path: str) -> DriverResult:
        browser = await self._require_browser()
        await browser.take_screenshot(path=save_path, format="png")
        return DriverResult(
            screenshot_path=save_path,
            url=await browser.get_current_page_url(),
            title=await browser.get_current_page_title(),
            message=f"Screenshot saved to {save_path}",
        )

    async def get_text(self, selector: str | None = None) -> DriverResult:
        browser = await self._require_browser()
        if selector:
            element = await self._resolve_element(selector)
            text = await element.evaluate("() => this.innerText")
        else:
            page = await self._require_page()
            text = await page.evaluate("() => document.body.innerText")

        return DriverResult(
            text=text or "",
            url=await browser.get_current_page_url(),
            title=await browser.get_current_page_title(),
            message="Extracted page text" if selector is None else f"Extracted text from {selector!r}",
        )

    async def scroll(self, direction: str = "down", amount: int = 500) -> DriverResult:
        if direction not in ("down", "up"):
            raise BrowserDriverError(
                f"Invalid scroll direction {direction!r}; expected 'down' or 'up'"
            )
        delta = amount if direction == "down" else -amount
        page = await self._require_page()
        await page.evaluate(f"() => window.scrollBy(0, {delta})")
        browser = await self._require_browser()
        return DriverResult(
            url=await browser.get_current_page_url(),
            message=f"Scrolled {direction} by {amount}px",
        )

    async def wait_for(
        self,
        selector: str,
        timeout: float = 30.0,
        poll_interval: float = 0.25,
    ) -> DriverResult:
        deadline = asyncio.get_event_loop().time() + timeout
        page = await self._require_page()

        while asyncio.get_event_loop().time() < deadline:
            elements = await page.get_elements_by_css_selector(selector)
            if elements:
                browser = await self._require_browser()
                return DriverResult(
                    url=await browser.get_current_page_url(),
                    message=f"Element {selector!r} appeared",
                )
            await asyncio.sleep(poll_interval)

        raise BrowserDriverError(
            f"Timed out after {timeout}s waiting for selector {selector!r}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _require_browser(self) -> Browser:
        if not self.is_started or self._browser is None:
            raise BrowserNotStartedError(
                "Browser session is not started; call await driver.start() first"
            )
        return self._browser

    async def _require_page(self) -> Page:
        browser = await self._require_browser()
        page = await browser.get_current_page()
        if page is None:
            page = await browser.must_get_current_page()
        return page

    async def _resolve_element(
        self,
        selector: str,
        *,
        exactly_one: bool = True,
    ) -> Element:
        page = await self._require_page()
        elements = await page.get_elements_by_css_selector(selector)
        if not elements:
            raise ElementNotFoundError(selector)
        if exactly_one and len(elements) > 1:
            raise AmbiguousSelectorError(selector, len(elements))
        return elements[0]
