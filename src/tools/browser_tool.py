"""
Browser automation tool powered by browser-use + OpenRouter.

Provides 16 distinct capabilities:
  1. Search + Compare on Booking Flows
  2. Authenticated Login + Dashboard Read
  3. Form Fill + Submission Confirmation
  4. Client-Side Filter Interaction
  5. Web Scraping / Data Extraction
  6. Navigation to Specific Pages
  7. Content Interaction
  8. General Information Gathering
  9. Multi-Step Workflows
 10. Testing and Validation
 11. Session Persistence
 12. Structured Typed Output
 13. Explicit Action Primitives
 14. Graceful Stuck-State Handling
 15. Human-in-the-Loop (HITL) Approval
 16. Sandboxed Execution

All actions return a structured ``BrowserToolResult`` (Pydantic model) for
downstream systems to parse without guessing at unstructured text.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import tempfile
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Type

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .browser_driver import BrowserDriver, BrowserDriverError
from .untrusted_content import scan_for_injection, wrap_web_content

load_dotenv()

# ---------------------------------------------------------------------------
# Feature 12 — Structured Typed Output
# ---------------------------------------------------------------------------

class ActionStatus(str, Enum):
    """Outcome status of a single browser action."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"


class BrowserToolResult(BaseModel):
    """
    Standardised result payload for every browser action.

    Downstream code should never need to regex-parse a free-text blob;
    every field is typed and predictable.
    """
    success: bool = False
    status: ActionStatus = ActionStatus.FAILED
    page_title: Optional[str] = None
    current_url: Optional[str] = None
    extracted_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None
    action_log: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def summary(self, max_text: int = 500) -> str:
        """Human-readable one-liner used in step results."""
        text_preview = ""
        if self.extracted_text:
            t = self.extracted_text
            text_preview = t[:max_text] + ("..." if len(t) > max_text else "")
        parts = [f"[{self.status.value}]"]
        if self.page_title:
            parts.append(f"title={self.page_title!r}")
        if self.current_url:
            parts.append(f"url={self.current_url}")
        if text_preview:
            parts.append(f"text={text_preview!r}")
        if self.error:
            parts.append(f"error={self.error!r}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Feature 13 — Explicit Action Primitives  (enum of supported actions)
# ---------------------------------------------------------------------------

class BrowserAction(str, Enum):
    """All recognised action verbs the tool can execute."""
    # Core primitives
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT_OPTION = "select_option"
    SCREENSHOT = "screenshot"
    GET_TEXT = "get_text"
    SCROLL = "scroll"
    WAIT_FOR = "wait_for"
    # High-level agent-driven
    RUN_TASK = "run_task"
    # Composite helpers
    SEARCH_AND_COMPARE = "search_and_compare"
    LOGIN = "login"
    FILL_FORM = "fill_form"
    APPLY_FILTER = "apply_filter"
    SCRAPE = "scrape"
    EXTRACT_TABLE = "extract_table"
    MULTI_STEP = "multi_step"
    VALIDATE = "validate"
    # Session
    CLOSE_SESSION = "close_session"


# ---------------------------------------------------------------------------
# Default configuration from environment
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = os.getenv(
    "BROWSER_USE_MODEL",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)
_VISION_MODEL = os.getenv(
    "BROWSER_USE_VISION_MODEL",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # Vision-capable model
)
_FALLBACK_MODEL = os.getenv(
    "BROWSER_FALLBACK_MODEL",
    "meta-llama/llama-3.1-8b-instruct:free",  # Reasonable free fallback
)
_DEFAULT_TIMEOUT = int(os.getenv("BROWSER_USE_TIMEOUT", "60"))
_LLM_TIMEOUT = int(os.getenv("BROWSER_LLM_TIMEOUT", "120"))  # Per-call LLM timeout (fix #2)
_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() in ("1", "true", "yes")
_SANDBOX_MODE = os.getenv("BROWSER_USE_SANDBOX", "false").lower() in ("1", "true", "yes")
_DOMAIN_ALLOWLIST = [
    d.strip()
    for d in os.getenv("BROWSER_USE_DOMAIN_ALLOWLIST", "").split(",")
    if d.strip()
]


# ---------------------------------------------------------------------------
# Feature 16 — Sandboxed Execution  (lightweight: headless + timeout + domain)
# ---------------------------------------------------------------------------

def _apply_sandbox_config() -> dict:
    """
    Return BrowserConfig kwargs that harden the browser for sandboxed runs.

    This is NOT container-level isolation — it's a process-level hardening
    layer (headless, restricted timeouts, domain allowlisting via navigation
    guards).  The project's container sandbox lives in agent-infra/sandbox;
    this module is the lighter tier.
    """
    return {
        "headless": True,
        "disable_security": False,
    }


# ---------------------------------------------------------------------------
# BrowserTool — the main class
# ---------------------------------------------------------------------------

class BrowserTool:
    """
    Stateful browser automation facade.

    A single instance should be reused for the lifetime of one plan-run
    (Feature 11 — Session Persistence) and closed when the plan finishes.
    """

    def __init__(
        self,
        headless: bool | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        sandbox_mode: bool = _SANDBOX_MODE,
        model: str = _DEFAULT_MODEL,
    ):
        self._headless = headless if headless is not None else _HEADLESS
        self._timeout = timeout
        self._sandbox_mode = sandbox_mode
        self._model = model

        # Lazy-initialised to avoid import errors if browser-use isn't installed
        self._browser = None
        self._browser_context = None
        self._llm = None
        self._action_log: list[str] = []
        self._session_active = False
        self._agent = None  # Reuse single Agent across plan steps (fix #3)
        self._last_url: str | None = None  # Track last known URL for session rebuild (fix #1)
        self._original_goal: str | None = None  # Track original goal for context (fix #1)
        self._rebuild_count = 0  # Cap recovery to one rebuild per step (fix #4)

        # BrowserDriver for deterministic primitives (Phase 2)
        self._driver = BrowserDriver(
            headless=self._headless,
            allowed_domains=_DOMAIN_ALLOWLIST or None,
            sandbox_mode=self._sandbox_mode,
        )

    # ------------------------------------------------------------------
    # Lazy init helpers
    # ------------------------------------------------------------------

    def _ensure_llm(self):
        """Initialise the OpenRouter LLM once."""
        if self._llm is not None:
            return
        from browser_use.llm import ChatOpenRouter

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not found in environment. "
                "Browser automation requires an OpenRouter API key."
            )
        self._llm = ChatOpenRouter(model=self._model, api_key=api_key)

    async def _check_session_health(self) -> bool:
        """
        Lightweight health check for the CDP session.
        
        Attempts to get the current page URL with a short timeout.
        Returns True if the session is healthy, False if it's dead/half-dead.
        """
        if self._browser is None:
            return False
        
        try:
            # Use a very short timeout for the health check
            await asyncio.wait_for(
                self._browser.get_current_page_url(),
                timeout=3.0
            )
            return True
        except Exception:
            # Any exception means the session is dead (CDP closed, queue shut down, etc.)
            return False

    async def _ensure_browser(self):
        """Create (or reuse) a Browser + BrowserContext (Feature 11)."""
        # Check session health before reusing (fix #1, fix #3)
        if self._browser is not None and self._session_active:
            if await self._check_session_health():
                return
            # Session is dead despite flag being True - force rebuild proactively
            self._log("Session health check failed, rebuilding proactively before operation...")
            try:
                await self.close_session()
            except Exception:
                # Swallow errors during teardown of a dead session
                pass

        from browser_use import Browser

        config_kwargs: dict[str, Any] = {"headless": self._headless, "keep_alive": True}
        if self._sandbox_mode:
            config_kwargs.update(_apply_sandbox_config())

        self._browser = Browser(**config_kwargs)
        self._session_active = True
        self._log("Browser session created (headless={}, sandbox={})".format(
            config_kwargs.get("headless"), self._sandbox_mode,
        ))

        # Share the browser instance with the driver (Phase 2)
        self._driver._browser = self._browser
        self._driver._owns_browser = False
        await self._driver.start()

    def set_original_goal(self, goal: str):
        """Set the original goal for context during session rebuilds (fix #1)."""
        self._original_goal = goal
        self._log(f"Set original goal: {goal[:100]}{'...' if len(goal) > 100 else ''}")

    def reset_rebuild_count(self):
        """Reset rebuild count for a new plan step (fix #4)."""
        self._rebuild_count = 0

    async def close_session(self):
        """Tear down the browser cleanly (end of plan run)."""
        # Run all close operations concurrently with shorter timeouts (fix #5)
        # This reduces recovery time from 60s+ to ~5s when session is already dead
        close_tasks = []
        
        # Close driver (Phase 2)
        if self._driver is not None:
            close_tasks.append(asyncio.create_task(
                asyncio.wait_for(self._driver.close(), timeout=5.0)
            ))
        
        # Close Agent if it exists
        if self._agent is not None:
            close_tasks.append(asyncio.create_task(
                asyncio.wait_for(self._agent.close(), timeout=5.0)
            ))
        
        # Close browser if it exists
        if self._browser is not None:
            close_tasks.append(asyncio.create_task(
                asyncio.wait_for(self._browser.close(), timeout=5.0)
            ))
        
        # Wait for all close operations to complete (or timeout)
        if close_tasks:
            results = await asyncio.gather(*close_tasks, return_exceptions=True)
            
            # Log any errors but don't fail the whole close operation
            for i, result in enumerate(results):
                if isinstance(result, asyncio.TimeoutError):
                    self._log(f"WARNING: Close operation {i} timed out after 5s, forcing cleanup")
                elif isinstance(result, Exception):
                    self._log(f"WARNING: Close operation {i} error: {result}")
        
        # Clear references regardless of close success
        self._agent = None
        self._browser = None
        self._browser_context = None
        self._session_active = False
        self._log("Browser session closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str):
        entry = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
        self._action_log.append(entry)
        print(f"🌐 {entry}")

    def _make_result(self, **overrides) -> BrowserToolResult:
        """Build a result, always attaching the current action log."""
        log_snapshot = list(self._action_log)
        # Clear per-action log for next action (keeps session log trimmed)
        self._action_log.clear()
        
        # Phase 3b: Apply injection wrapper to web-derived content
        metadata = overrides.get("metadata", {})
        extracted_text = overrides.get("extracted_text")
        page_title = overrides.get("page_title")
        current_url = overrides.get("current_url")
        
        if extracted_text and current_url and not metadata.get("injection_flagged"):
            if scan_for_injection(extracted_text):
                metadata["injection_flagged"] = True
                self._log("INJECTION DETECTED in extracted_text")
            else:
                extracted_text = wrap_web_content(extracted_text, current_url)
        
        if page_title and current_url and not metadata.get("injection_flagged"):
            if scan_for_injection(page_title):
                metadata["injection_flagged"] = True
                self._log("INJECTION DETECTED in page_title")
            else:
                page_title = wrap_web_content(page_title, current_url)
        
        overrides["extracted_text"] = extracted_text
        overrides["page_title"] = page_title
        overrides["metadata"] = metadata
        
        return BrowserToolResult(action_log=log_snapshot, **overrides)

    def _driver_result_to_tool_result(
        self, driver_result, source_url: str | None = None
    ) -> BrowserToolResult:
        """Map DriverResult to BrowserToolResult (Phase 2)."""
        return self._make_result(
            success=True,
            status=ActionStatus.SUCCESS,
            current_url=driver_result.url or source_url,
            page_title=driver_result.title,
            extracted_text=driver_result.text or driver_result.message,
            screenshot_path=driver_result.screenshot_path,
        )

    def _error_result(self, error: str, status: ActionStatus = ActionStatus.FAILED) -> BrowserToolResult:
        self._log(f"ERROR: {error}")
        return self._make_result(success=False, status=status, error=error)

    def _timeout_result(self, action: str) -> BrowserToolResult:
        msg = f"Timeout ({self._timeout}s) exceeded during: {action}"
        self._log(msg)
        return self._make_result(success=False, status=ActionStatus.TIMEOUT, error=msg)

    # ------------------------------------------------------------------
    # Feature 14 — Graceful Stuck-State Handling
    # ------------------------------------------------------------------

    async def _with_timeout(self, coro, action_name: str):
        """
        Wrap any async operation with a timeout.  On timeout, returns a
        TIMEOUT result instead of crashing the workflow.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        except asyncio.TimeoutError:
            return self._timeout_result(action_name)
        except Exception as e:
            return self._error_result(
                f"{action_name} failed: {type(e).__name__}: {e}"
            )

    # ------------------------------------------------------------------
    # Feature 15 — HITL Approval gate
    # ------------------------------------------------------------------

    _hitl_callback = None  # Set by use_browser_node to hook into interrupt()

    @classmethod
    def set_hitl_callback(cls, callback):
        """
        Register a callback ``callback(action_description) -> bool`` that
        returns True if the human approves the action, False to abort.

        The callback is set once by the graph node and used by every
        ``require_approval()`` call in this instance.
        """
        cls._hitl_callback = callback

    def require_approval(self, action_desc: str) -> bool:
        """
        Gate an irreversible action behind human approval.

        Returns True if approved (or no HITL callback is registered — i.e.
        running outside the graph in a script context where everything is
        implicitly approved).
        """
        if self._hitl_callback is None:
            return True
        self._log(f"HITL: requesting approval for: {action_desc}")
        return self._hitl_callback(action_desc)

    # ==================================================================
    # Feature 13 — Explicit Action Primitives
    # ==================================================================

    async def navigate(self, url: str) -> BrowserToolResult:
        """Navigate to a URL and return page title + current URL."""
        self._log(f"navigate → {url}")
        await self._ensure_browser()

        try:
            result = await self._driver.navigate(url)
            return self._driver_result_to_tool_result(result, source_url=url)
        except asyncio.TimeoutError:
            return self._timeout_result(f"navigate({url})")
        except BrowserDriverError as e:
            return self._error_result(f"navigate failed: {e}")
        except Exception as e:
            return self._error_result(f"navigate failed: {e}")

    async def click(self, selector: str) -> BrowserToolResult:
        """Click an element identified by CSS selector or description."""
        self._log(f"click → {selector}")
        await self._ensure_browser()

        # Phase 3c: HITL gating for submit-like clicks
        selector_lower = selector.lower()
        submit_patterns = [
            r"\[type=submit\]",
            r"button\[type=submit\]",
            r"\bsubmit\b",
            r"\bbook\b",
            r"\bpay\b",
            r"\bcheckout\b",
            r"\bconfirm\b",
            r"\bpurchase\b",
            r"\bdelete\b",
            r"\bremove\b",
        ]
        
        is_submit_like = any(
            re.search(pattern, selector_lower) for pattern in submit_patterns
        )
        
        if is_submit_like:
            if not self.require_approval(
                f"Click potentially irreversible element: {selector}"
            ):
                return self._make_result(
                    success=False,
                    status=ActionStatus.NEEDS_APPROVAL,
                    error="Human rejected click action",
                )

        try:
            result = await self._driver.click(selector)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"click({selector})")
        except BrowserDriverError as e:
            return self._error_result(f"click failed: {e}")
        except Exception as e:
            return self._error_result(f"click failed: {e}")

    async def fill(self, selector: str, value: str) -> BrowserToolResult:
        """Fill a form field identified by selector with the given value."""
        self._log(f"fill → {selector} = {value[:50]}{'...' if len(value) > 50 else ''}")
        await self._ensure_browser()

        try:
            result = await self._driver.fill(selector, value)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"fill({selector})")
        except BrowserDriverError as e:
            return self._error_result(f"fill failed: {e}")
        except Exception as e:
            return self._error_result(f"fill failed: {e}")

    async def select_option(self, selector: str, value: str) -> BrowserToolResult:
        """Select an option from a dropdown/select element."""
        self._log(f"select_option → {selector} = {value}")
        await self._ensure_browser()

        try:
            result = await self._driver.select_option(selector, value)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"select_option({selector})")
        except BrowserDriverError as e:
            return self._error_result(f"select_option failed: {e}")
        except Exception as e:
            return self._error_result(f"select_option failed: {e}")

    async def screenshot(self, save_path: str | None = None) -> BrowserToolResult:
        """Take a screenshot of the current page."""
        self._log("screenshot")
        await self._ensure_browser()

        if not save_path:
            save_path = os.path.join(
                tempfile.gettempdir(),
                f"browser_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            )

        try:
            result = await self._driver.screenshot(save_path)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result("screenshot")
        except BrowserDriverError as e:
            return self._error_result(f"screenshot failed: {e}")
        except Exception as e:
            return self._error_result(f"screenshot failed: {e}")

    async def get_text(self, selector: str | None = None) -> BrowserToolResult:
        """Extract text content from the page or a specific element."""
        desc = selector or "entire page"
        self._log(f"get_text → {desc}")
        await self._ensure_browser()

        try:
            result = await self._driver.get_text(selector)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"get_text({desc})")
        except BrowserDriverError as e:
            return self._error_result(f"get_text failed: {e}")
        except Exception as e:
            return self._error_result(f"get_text failed: {e}")

    async def scroll(self, direction: str = "down", amount: int = 500) -> BrowserToolResult:
        """Scroll the page in the given direction."""
        self._log(f"scroll → {direction} by {amount}px")
        await self._ensure_browser()

        try:
            result = await self._driver.scroll(direction, amount)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"scroll({direction})")
        except BrowserDriverError as e:
            return self._error_result(f"scroll failed: {e}")
        except Exception as e:
            return self._error_result(f"scroll failed: {e}")

    async def wait_for(self, selector: str, timeout: float | None = None) -> BrowserToolResult:
        """Wait for an element to appear on the page."""
        wait_timeout = timeout or min(self._timeout, 30)
        self._log(f"wait_for → {selector} (timeout={wait_timeout}s)")
        await self._ensure_browser()

        try:
            result = await self._driver.wait_for(selector, wait_timeout)
            return self._driver_result_to_tool_result(result)
        except asyncio.TimeoutError:
            return self._timeout_result(f"wait_for({selector})")
        except BrowserDriverError as e:
            return self._error_result(f"wait_for failed: {e}")
        except Exception as e:
            return self._error_result(f"wait_for failed: {e}")

    # ==================================================================
    # High-level agent-driven tasks
    # ==================================================================

    async def run_task(
        self,
        task: str,
        output_model: Type[BaseModel] | None = None,
        max_steps: int = 25,
    ) -> BrowserToolResult:
        """
        Delegate a natural-language task to the browser-use Agent.

        This is the general-purpose entry point — most high-level features
        (e1–e4, 5–10) ultimately flow through here with appropriately
        crafted task prompts.
        
        Session lifecycle fixes:
        - Reuses a single Agent instance across plan steps via add_new_task() (fix #3)
        - Catches session-dead exceptions and retries with a fresh session (fix #2)
        - Proactively checks session health after completion (fix #4)
        - Prepend navigate to last URL on session rebuild (fix #1)
        - Cap recovery to one rebuild per step (fix #4)
        
        Known limitation: For multi-field forms, the agent's loop-detector shows
        it reliably loses track past ~5-6 fields in a single run_task call.
        Suggested: Break large form-fill tasks into multiple smaller steps
        (2-3 fields each) so mid-form failures only cost partial progress and
        the replanner can react. This is a planning-level change, not a tool-level fix.
        """
        self._log(f"run_task → {task[:120]}{'...' if len(task) > 120 else ''}")
        self._ensure_llm()
        await self._ensure_browser()

        # Import bubus for QueueShutDown exception handling (fix #2)
        try:
            import bubus.service
            _QueueShutDown = bubus.service.QueueShutDown
        except ImportError:
            _QueueShutDown = None

        # Session-dead exceptions to catch (fix #2)
        session_dead_exceptions = []
        if _QueueShutDown is not None:
            session_dead_exceptions.append(_QueueShutDown)
        # Add generic connection/CDP errors
        session_dead_exceptions.extend([
            ConnectionError,
            ConnectionRefusedError,
            ConnectionResetError,
        ])

        async def _execute_task(attempt: int = 1, retry_task: str | None = None) -> BrowserToolResult:
            """Inner function that accepts an optional modified task for retries."""
            actual_task = retry_task if retry_task is not None else task
            
            try:
                from browser_use import Agent

                # Reuse existing Agent if available (fix #3)
                # Proactively check session health before attempting reuse (fix #3)
                if self._agent is not None:
                    if not await self._check_session_health():
                        self._log("Agent exists but session is dead, forcing rebuild before reuse")
                        self._agent = None  # Force new Agent creation
                        self._session_active = False
                
                if self._agent is None:
                    # Configure fallback LLM for reliability (fix #1)
                    fallback_llm = None
                    if _FALLBACK_MODEL and _FALLBACK_MODEL != _DEFAULT_MODEL:
                        from browser_use.llm import ChatOpenRouter
                        fallback_llm = ChatOpenRouter(model=_FALLBACK_MODEL, api_key=os.getenv("OPENROUTER_API_KEY"))
                        self._log(f"Configured fallback LLM: {_FALLBACK_MODEL}")
                    
                    # Use vision model if vision is enabled and a separate vision model is configured
                    use_vision = _VISION_MODEL and _VISION_MODEL != _DEFAULT_MODEL
                    if use_vision:
                        # Create separate LLM instance for vision
                        from browser_use.llm import ChatOpenRouter
                        vision_llm = ChatOpenRouter(model=_VISION_MODEL, api_key=os.getenv("OPENROUTER_API_KEY"))
                        self._log(f"Using vision model: {_VISION_MODEL}")
                        agent_llm = vision_llm
                    else:
                        agent_llm = self._llm
                    
                    agent_kwargs: dict[str, Any] = {
                        "task": actual_task,
                        "llm": agent_llm,
                        "browser": self._browser,
                        "max_actions_per_step": 4,
                        "use_vision": use_vision,
                    }
                    if fallback_llm is not None:
                        agent_kwargs["llm"] = agent_llm  # Primary LLM
                        agent_kwargs["fallback_llm"] = fallback_llm  # Fallback (fix #1)
                    
                    self._agent = Agent(**agent_kwargs)
                    self._log("Created new Agent instance")
                else:
                    # Continue with existing Agent using add_new_task()
                    self._agent.add_new_task(actual_task)
                    self._log(f"Reusing existing Agent (attempt {attempt})")

                history = await asyncio.wait_for(self._agent.run(), timeout=_LLM_TIMEOUT)  # Use LLM timeout (fix #2)

                if history is None:
                    return self._error_result("Agent returned no history")

                # Detect silent-loop failure mode (fix #2)
                # Check for repeated identical actions or loop-detection events in history
                try:
                    if hasattr(history, 'history') and history.history:
                        action_sequence = []
                        for step in history.history:
                            if hasattr(step, 'action') and step.action:
                                action_str = str(step.action)
                                action_sequence.append(action_str)
                        
                        # Check for repeated identical actions (3+ times)
                        if len(action_sequence) >= 3:
                            last_three = action_sequence[-3:]
                            if last_three[0] == last_three[1] == last_three[2]:
                                self._log(f"Detected silent loop: repeated action '{last_three[0]}' 3 times")
                                return self._error_result(
                                    f"Agent entered a silent loop repeating action '{last_three[0]}' "
                                    f"without completing the task. Task likely failed."
                                )
                        
                        # Check for loop-detection events in history
                        history_str = str(history.history)
                        if "loop detection" in history_str.lower() or "loop" in history_str.lower():
                            self._log("Detected loop-detection event in agent history")
                            # Check if final result is actually meaningful or just a premature submit
                            result_text = history.final_result()
                            if result_text and len(result_text) < 50:  # Suspiciously short result
                                self._log(f"Suspiciously short result after loop detection: '{result_text}'")
                                return self._error_result(
                                    f"Agent detected a loop and may have prematurely submitted. "
                                    f"Result: '{result_text}'. Task likely incomplete."
                                )
                except Exception as e:
                    # History inspection failed, but don't block execution
                    self._log(f"Could not inspect history for loop detection: {e}")

                result_text = history.final_result()
                if not result_text:
                    result_text = "Task completed but returned no text result"

                # Update last known URL after successful task (fix #1)
                try:
                    current_url = await self._browser.get_current_page_url()
                    if current_url:
                        self._last_url = current_url
                        self._log(f"Updated last known URL: {current_url}")
                except Exception:
                    pass  # URL tracking is best-effort

                # Proactive health check after successful completion (fix #4)
                if not await self._check_session_health():
                    self._log("Session health check failed after task completion, marking as degraded")
                    # Don't fail the result, but mark session as dead for next call
                    self._session_active = False

                return self._make_result(
                    success=True,
                    status=ActionStatus.SUCCESS,
                    extracted_text=result_text,
                    page_title=result_text[:120] if result_text else None,
                )
            except tuple(session_dead_exceptions) as e:
                # Session-dead exception caught (fix #2)
                self._log(f"Session-dead exception caught: {type(e).__name__}: {e}")
                self._session_active = False
                
                # Cap recovery to one rebuild per step (fix #4)
                if self._rebuild_count >= 1:
                    self._log("Rebuild limit reached (1 per step), surfacing error to graph")
                    return self._error_result(
                        f"Session died during task execution and rebuild limit exceeded: {e}"
                    )
                
                self._rebuild_count += 1
                
                if attempt == 1:
                    # Retry once with a fresh session
                    self._log("Retrying task with fresh session...")
                    try:
                        await self.close_session()
                    except Exception:
                        pass  # Swallow errors during teardown of dead session
                    
                    # Rebuild with bounded timeout to fail fast instead of hanging
                    try:
                        # Agent is now None (set by close_session), safe to rebuild
                        await asyncio.wait_for(self._ensure_browser(), timeout=30.0)
                    except asyncio.TimeoutError:
                        self._log("Session rebuild timed out after 30s, failing fast to replanner")
                        return self._error_result(
                            f"Session rebuild timed out - browser session may be in corrupted state: {e}"
                        )
                    
                    # Prepend navigate to last known URL if available (fix #1)
                    retry_task = task
                    if self._last_url:
                        self._log(f"Prepending navigate to {self._last_url} for session rebuild continuity")
                        retry_task = f"First, navigate to {self._last_url}. Then: {task}"
                    
                    return await _execute_task(attempt=2, retry_task=retry_task)
                else:
                    # Second attempt also failed
                    return self._error_result(f"Session died during task execution: {e}")
            except asyncio.TimeoutError:
                return self._timeout_result(f"run_task")
            except Exception as e:
                # Detect index-not-found errors after dropdown operations (fix #4)
                error_str = str(e)
                if "Element index" in error_str and "not available" in error_str:
                    self._log(f"Detected index-not-found error: {e}")
                    self._log("This suggests a dropdown/index mismatch. Consider using select_option() for deterministic selection.")
                    # Try to recover by suggesting the deterministic path
                    # We can't automatically retry with the deterministic helper without knowing the selector,
                    # but we surface a clear error message to guide the planner or caller
                    return self._error_result(
                        f"Dropdown selection failed due to index mismatch: {e}. "
                        "Use select_option(selector, value) for reliable <select> handling."
                    )
                return self._error_result(f"run_task failed: {e}")

        return await _execute_task()

    # ==================================================================
    # Feature e1 — Search + Compare on a Booking Flow
    # ==================================================================

    async def search_and_compare(
        self,
        task: str,
        criteria: str = "cheapest",
    ) -> BrowserToolResult:
        """
        Navigate a booking interface, read multiple results, extract fares,
        and compare them against the requested criteria.
        """
        prompt = (
            f"{task}\n\n"
            f"Instructions:\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify elements, read visual content, and understand the page layout.\n\n"
            f"1. Navigate to the booking/search page.\n"
            f"2. Read ALL available search results (scroll if needed).\n"
            f"3. Extract details for each option: name/carrier, price/fare, "
            f"   departure/arrival times, duration, stops.\n"
            f"4. Compare all options and identify the {criteria} option.\n"
            f"5. Return a structured summary with ALL options listed, and "
            f"   clearly mark which is the {criteria}.\n"
            f"Format each option as: Option N: [details] — $price"
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature e2 — Authenticated Login + Dashboard Read
    # ==================================================================

    async def login(
        self,
        url: str,
        username: str,
        password: str,
        username_selector: str = "",
        password_selector: str = "",
        submit_selector: str = "",
        dashboard_wait: str = "",
    ) -> BrowserToolResult:
        """
        Log into a website and extract information from the rendered dashboard.
        Reads the actual rendered UI, not raw HTML source.
        """
        selector_hints = ""
        if username_selector:
            selector_hints += f"\n- Username field selector: {username_selector}"
        if password_selector:
            selector_hints += f"\n- Password field selector: {password_selector}"
        if submit_selector:
            selector_hints += f"\n- Submit button selector: {submit_selector}"

        wait_hint = ""
        if dashboard_wait:
            wait_hint = f"\n4. Wait for the element '{dashboard_wait}' to confirm the dashboard has loaded."

        prompt = (
            f"Login to {url} and read the authenticated dashboard.\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify form fields, buttons, and read the rendered dashboard content.\n\n"
            f"CRITICAL: Fill username and password in a SINGLE coordinated action - do not fill one field at a time. "
            f"Use vision to identify both field positions first, then fill them sequentially in one pass.\n\n"
            f"Steps:\n"
            f"1. Navigate to {url}\n"
            f"2. Use vision to identify the login form fields (username and password) in one pass\n"
            f"3. Fill BOTH fields at once:\n"
            f"   - Username/email: {username}\n"
            f"   - Password: {password}\n"
            f"{selector_hints}\n"
            f"4. Submit the login form and wait for the dashboard to fully render.\n"
            f"{wait_hint}\n"
            f"5. Read and extract the VISIBLE information displayed on the "
            f"dashboard page (do NOT read raw HTML source).\n"
            f"6. Return a structured summary of all dashboard content: "
            f"metrics, notifications, recent activity, etc."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature e3 — Form Fill + Submission Confirmation
    # ==================================================================

    async def fill_form(
        self,
        url: str,
        fields: dict[str, str],
        submit_selector: str = "",
    ) -> BrowserToolResult:
        """
        Populate a form with the provided field values, submit it, and
        verify the submission was confirmed by the website.
        
        Integrates with UserInfoStore to auto-fill known values.
        """
        # Integrate with UserInfoStore for auto-fill (fix #5)
        from .user_info_store import get_user_info_store
        
        store = get_user_info_store()
        
        # Pre-fill fields from store if not already provided
        for key in fields.keys():
            if not fields[key]:  # If field value is empty
                stored_value = store.get_info(key)
                if stored_value:
                    fields[key] = stored_value
                    self._log(f"Auto-filled {key} from user info store")
        
        # Feature 15 — HITL gate for form submission (irreversible)
        if not self.require_approval(
            f"Fill and submit form at {url} with {len(fields)} fields"
        ):
            return self._make_result(
                success=False,
                status=ActionStatus.NEEDS_APPROVAL,
                error="Human rejected form submission",
            )

        field_lines = "\n".join(
            f"   - {label}: {value}" for label, value in fields.items()
        )
        submit_hint = (
            f"\n3. Click the submit button (selector: {submit_selector})."
            if submit_selector
            else "\n3. Find and click the submit button."
        )

        prompt = (
            f"Fill out and submit the form at {url}.\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify form fields, buttons, and verify submission success visually.\n\n"
            f"CRITICAL: Fill ALL fields in a SINGLE coordinated action - do not fill one field at a time. "
            f"Use vision to identify all field positions first, then fill them sequentially in one pass.\n\n"
            f"Steps:\n"
            f"1. Navigate to {url}\n"
            f"2. Use vision to identify ALL form fields and their positions in one pass\n"
            f"3. Fill ALL fields at once with these values:\n{field_lines}\n"
            f"{submit_hint}\n"
            f"4. Wait for the page to respond after submission.\n"
            f"5. Verify the submission was successful by checking for:\n"
            f"   - A success message on the page, OR\n"
            f"   - A redirect to a confirmation page, OR\n"
            f"   - A confirmation banner/toast\n"
            f"6. Return the confirmation message or page content that "
            f"proves submission succeeded. If submission failed, report "
            f"the error message shown on the page."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature e4 — Client-Side Filter Interaction
    # ==================================================================

    async def apply_filter(
        self,
        url: str,
        filter_actions: list[dict[str, str]],
    ) -> BrowserToolResult:
        """
        Interact with UI controls (dropdowns, checkboxes, sliders) that
        dynamically update page content, then read the updated results.

        ``filter_actions`` is a list of dicts, each with:
            {"type": "dropdown|checkbox|slider|click", "selector": "...", "value": "..."}
        """
        action_lines = []
        for i, fa in enumerate(filter_actions, 1):
            ftype = fa.get("type", "click")
            sel = fa.get("selector", "")
            val = fa.get("value", "")
            if ftype == "dropdown":
                action_lines.append(f"   {i}. Select '{val}' from dropdown '{sel}'")
            elif ftype == "checkbox":
                action_lines.append(f"   {i}. {'Check' if val.lower() in ('true', '1', 'on') else 'Uncheck'} the checkbox '{sel}'")
            elif ftype == "slider":
                action_lines.append(f"   {i}. Set slider '{sel}' to value {val}")
            else:
                action_lines.append(f"   {i}. Click element '{sel}'")

        prompt = (
            f"Apply filters on {url} and read the updated results.\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify filter controls (dropdowns, checkboxes, sliders) and observe "
            f"when content updates.\n\n"
            f"Steps:\n"
            f"1. Navigate to {url}\n"
            f"2. Apply these filter actions:\n"
            f"{chr(10).join(action_lines)}\n"
            f"3. WAIT for the page content to update after each filter "
            f"   (do NOT read stale/original content).\n"
            f"4. After all filters are applied, extract the NEWLY RENDERED "
            f"   results from the page.\n"
            f"5. Return the filtered results in a structured format."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature 5 — Web Scraping / Data Extraction
    # ==================================================================

    async def scrape(
        self,
        url: str,
        extract: str = "all visible text",
    ) -> BrowserToolResult:
        """
        Collect structured information from a web page.
        Returns extracted content in clean, machine-readable format.
        """
        prompt = (
            f"Scrape data from {url}.\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify content sections, tables, lists, and distinguish between relevant "
            f"content and navigation/ads.\n\n"
            f"What to extract: {extract}\n\n"
            f"Instructions:\n"
            f"1. Navigate to {url}\n"
            f"2. Wait for the page to fully load (including dynamic content).\n"
            f"3. Extract the requested information: {extract}\n"
            f"4. If the content is in a table, preserve the table structure.\n"
            f"5. If pagination exists, note total pages but extract the current page.\n"
            f"6. Return the data in a clean, structured format:\n"
            f"   - Tables: one row per line, pipe-separated columns\n"
            f"   - Lists: one item per line\n"
            f"   - Key-value: 'Key: Value' format\n"
            f"7. Remove navigation elements, ads, and irrelevant content."
        )
        return await self.run_task(prompt)

    async def extract_table(self, url: str, table_selector: str = "") -> BrowserToolResult:
        """Extract a table from a web page into structured format."""
        sel_hint = f" identified by '{table_selector}'" if table_selector else ""
        prompt = (
            f"Extract the data table{sel_hint} from {url}.\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify tables visually, distinguish headers from data, and ensure you "
            f"capture the complete table structure.\n\n"
            f"Instructions:\n"
            f"1. Navigate to {url}\n"
            f"2. Locate the table{sel_hint}.\n"
            f"3. Extract ALL rows and columns.\n"
            f"4. Return in this format:\n"
            f"   Header1 | Header2 | Header3\n"
            f"   Value1  | Value2  | Value3\n"
            f"   ...\n"
            f"5. Preserve all data — do not truncate or summarize."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature 9 — Multi-Step Workflows
    # ==================================================================

    async def multi_step(
        self,
        steps: list[str],
    ) -> BrowserToolResult:
        """
        Execute a sequence of related actions, maintaining continuity
        across the workflow so each step builds on the previous one.
        """
        step_lines = "\n".join(f"   Step {i}: {s}" for i, s in enumerate(steps, 1))
        prompt = (
            f"Execute this multi-step workflow in sequence:\n\n"
            f"You have VISION capabilities - you can SEE the page visually. Use this to "
            f"identify elements, verify actions completed successfully, and understand "
            f"page state changes between steps.\n\n"
            f"{step_lines}\n\n"
            f"CRITICAL RULES:\n"
            f"- Execute steps IN ORDER. Do not skip or reorder.\n"
            f"- Each step builds on the previous one's result.\n"
            f"- If a step fails, STOP and report which step failed and why.\n"
            f"- Do NOT start from scratch between steps — maintain the current "
            f"browser state (URL, form data, login session).\n"
            f"- After completing ALL steps, return a summary of each step's "
            f"outcome."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Feature 10 — Testing and Validation
    # ==================================================================

    async def validate(
        self,
        url: str,
        checks: list[dict[str, str]],
    ) -> BrowserToolResult:
        """
        Verify that website features behave as expected.

        ``checks`` is a list of dicts:
            {"action": "description", "expected": "expected outcome"}
        """
        check_lines = []
        for i, c in enumerate(checks, 1):
            action = c.get("action", "")
            expected = c.get("expected", "")
            check_lines.append(
                f"   Check {i}:\n"
                f"     Action: {action}\n"
                f"     Expected: {expected}"
            )

        prompt = (
            f"Test and validate features on {url}.\n\n"
            f"For each check below, perform the action and verify the result "
            f"matches the expected outcome:\n\n"
            f"{chr(10).join(check_lines)}\n\n"
            f"For each check, report:\n"
            f"- PASS: if the actual result matches the expected outcome\n"
            f"- FAIL: if it doesn't match, explaining what was found instead\n"
            f"Return a summary: X/Y checks passed."
        )
        return await self.run_task(prompt)

    # ==================================================================
    # Dispatcher — routes action string to the right method
    # ==================================================================

    async def execute(
        self,
        action: str,
        task: str = "",
        url: str = "",
        selector: str = "",
        value: str = "",
        credentials: dict | None = None,
        fields: dict | None = None,
        filter_actions: list | None = None,
        steps: list | None = None,
        checks: list | None = None,
        criteria: str = "cheapest",
        extract: str = "all visible text",
        save_path: str | None = None,
        direction: str = "down",
        amount: int = 500,
        timeout: float | None = None,
        output_model: Type[BaseModel] | None = None,
    ) -> BrowserToolResult:
        """
        Central dispatcher — routes an action string to the appropriate
        method.  Called by ``browser_use_tool()`` in registry.py.
        """
        action_lower = action.lower().strip()

        try:
            # --- Primitives ---
            if action_lower == BrowserAction.NAVIGATE:
                return await self.navigate(url or task)

            if action_lower == BrowserAction.CLICK:
                return await self.click(selector or task)

            if action_lower == BrowserAction.FILL:
                return await self.fill(selector, value)

            if action_lower == BrowserAction.SELECT_OPTION:
                return await self.select_option(selector, value)

            if action_lower == BrowserAction.SCREENSHOT:
                return await self.screenshot(save_path)

            if action_lower == BrowserAction.GET_TEXT:
                return await self.get_text(selector or None)

            if action_lower == BrowserAction.SCROLL:
                return await self.scroll(direction, amount)

            if action_lower == BrowserAction.WAIT_FOR:
                return await self.wait_for(selector, timeout)

            # --- High-level ---
            if action_lower == BrowserAction.RUN_TASK:
                return await self.run_task(task, output_model=output_model)

            if action_lower == BrowserAction.SEARCH_AND_COMPARE:
                return await self.search_and_compare(task, criteria)

            if action_lower == BrowserAction.LOGIN:
                creds = credentials or {}
                return await self.login(
                    url=url or task,
                    username=creds.get("username", ""),
                    password=creds.get("password", ""),
                    username_selector=creds.get("username_selector", ""),
                    password_selector=creds.get("password_selector", ""),
                    submit_selector=creds.get("submit_selector", ""),
                    dashboard_wait=creds.get("dashboard_wait", ""),
                )

            if action_lower == BrowserAction.FILL_FORM:
                return await self.fill_form(
                    url=url or task,
                    fields=fields or {},
                    submit_selector=selector,
                )

            if action_lower == BrowserAction.APPLY_FILTER:
                return await self.apply_filter(
                    url=url or task,
                    filter_actions=filter_actions or [],
                )

            if action_lower == BrowserAction.SCRAPE:
                return await self.scrape(url=url or task, extract=extract)

            if action_lower == BrowserAction.EXTRACT_TABLE:
                return await self.extract_table(url=url or task, table_selector=selector)

            if action_lower == BrowserAction.MULTI_STEP:
                return await self.multi_step(steps=steps or [task])

            if action_lower == BrowserAction.VALIDATE:
                return await self.validate(url=url or task, checks=checks or [])

            if action_lower == BrowserAction.CLOSE_SESSION:
                await self.close_session()
                return self._make_result(
                    success=True,
                    status=ActionStatus.SUCCESS,
                    extracted_text="Browser session closed",
                )

            # Fallback — treat the action string as a free-form task
            return await self.run_task(task or action)

        except Exception as e:
            tb = traceback.format_exc()
            return self._error_result(
                f"execute({action_lower}) unhandled error: {e}\n{tb}"
            )


# ---------------------------------------------------------------------------
# Module-level singleton for session persistence across a plan run
# (Feature 11) — created on first use, closed by close_session().
# ---------------------------------------------------------------------------

_active_browser_tool: BrowserTool | None = None


def get_browser_tool(**kwargs) -> BrowserTool:
    """
    Return the active BrowserTool singleton, creating one if needed.

    The singleton persists for the entire plan run (preserving cookies,
    login state, browser context).  Call ``close_browser_tool()`` at the
    end of the plan to tear it down.
    """
    global _active_browser_tool
    if _active_browser_tool is None:
        _active_browser_tool = BrowserTool(**kwargs)
    return _active_browser_tool


async def close_browser_tool():
    """Tear down the active browser session (end of plan run)."""
    global _active_browser_tool
    if _active_browser_tool is not None:
        await _active_browser_tool.close_session()
        _active_browser_tool = None


# ---------------------------------------------------------------------------
# Synchronous wrapper for use in registry.py / nodes.py
# ---------------------------------------------------------------------------

def _run_async(coro):
    """
    Run an async coroutine from synchronous code, handling the case where
    an event loop may or may not already be running.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
