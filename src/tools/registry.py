from tavily import TavilyClient
from dotenv import load_dotenv
import os
import re

from src.sandbox.shell_runner import run_shell_command, write_file as sandbox_write_file, delete_path as sandbox_delete_path, ALLOWED_COMMANDS
from src.sandbox.server_manager import start_dev_server

load_dotenv()

client = TavilyClient(os.getenv("TAVILY_API_KEY"))

_NOISE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"subscribe", r"follow", r"channel", r"nav", r"footer", r"menu",
    r"subscribers?", r"views", r"like", r"share", r"comment",
    r"FOLLOW.*CHANNELS?", r"SUBSCRIBE", r"©\s*\d{4}",
    r"privacy policy", r"terms of service", r"cookie",
))
_EXCESSIVE_PUNCTUATION = re.compile(r"[!?.]{3,}")


def _filter_noise(content: str) -> str:
    """
    Filter out navigation bars, footers, and other noise from search results.
    Removes lines containing common navigation/footer patterns.
    """
    lines = content.split("\n")
    filtered_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        # Skip lines that match noise patterns (case-insensitive)
        if any(pattern.search(line_stripped) for pattern in _NOISE_PATTERNS):
            continue
        
        # Skip lines that are all caps (likely headers/ads)
        if line_stripped.isupper() and len(line_stripped) > 3:
            continue
        
        # Skip lines with excessive punctuation (likely ads/promotions)
        if _EXCESSIVE_PUNCTUATION.search(line_stripped):
            continue
        
        filtered_lines.append(line)
    
    return "\n".join(filtered_lines)


def tavily_search(query: str, search_depth: str = "basic", recency_sensitive: bool = False) -> str:
    """
    Use web search to get relevant information using Tavily and return a response.

    Args:
        query: The search query string
        search_depth: Either "basic" or "advanced" - basic for status checks, advanced for detailed searches
        recency_sensitive: If True, biases the search toward live/current results using
            Tavily's topic="news" mode plus a tight time_range, instead of general web
            search. This matters because "days=7" alone does not reliably filter out
            stale content — Wikipedia-style reference pages and SEO aggregator content
            often pass a raw day-count filter even though the actual FACTS on the page
            span multiple years (e.g. a "F1 winners" page updated last week that still
            lists a 2025 race as if current). topic="news" applies much stronger
            recency weighting on top of any day/time_range filter. Callers should pass
            True for goals/steps carrying recency language ("latest", "recent",
            "current", "this year", etc.) — see _needs_date_anchor in
            plan_execute/nodes.py, which already detects this same signal for the
            date-anchor feature and can be reused here.

    Returns:
        Filtered search results with noise removed
    """
    params = {
        "query": query,
        "search_depth": search_depth,
        "chunks_per_source": 3,
        "max_results": 3,
        "include_answer": False,
        "include_raw_content": False,
    }

    if recency_sensitive:
        # topic="news" applies much stronger recency weighting than the default
        # "general" topic — general web search happily surfaces well-indexed
        # reference/historical pages (Wikipedia, stat sites) that a raw days=N
        # filter doesn't reliably exclude, since those pages' last-modified
        # timestamps can be recent even when the specific fact needed is stale.
        params["topic"] = "news"
        params["time_range"] = "week"
    else:
        # Non-recency-sensitive queries (e.g. static/historical facts) keep the
        # original loose day filter — no need to bias toward news sources.
        params["days"] = 7

    response = client.search(**params)

    if response.get("answer"):
        return _filter_noise(response["answer"])

    if response.get("results"):
        filtered_results = []
        for result in response["results"]:
            filtered_content = _filter_noise(result["content"])
            if filtered_content.strip():
                filtered_results.append(filtered_content)

        return "\n\n".join(filtered_results)

    return "No results found."


def today_date() -> str:
    """Return today's date in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Coding-agent tools — shell, file I/O, dev server
# ---------------------------------------------------------------------------

def shell_command_tool(command: str, workspace_path: str) -> str:
    """
    Run a shell command inside the agent workspace and return stdout or an
    error string. Wraps shell_runner.run_shell_command.

    Args:
        command: The command to run (e.g. "npm install", "npx create-vite@latest . --template react").
        workspace_path: Absolute path to the project workspace.

    Returns:
        stdout on success, or "ERROR: <message>\n<stderr>" on failure.
    """
    result = run_shell_command(command, cwd=workspace_path)
    if result.success:
        output = result.stdout.strip()
        return output if output else f"Command '{command}' completed successfully (no output)."
    else:
        parts = [f"ERROR: {result.error}"]
        if result.stderr and result.stderr.strip():
            parts.append(f"stderr: {result.stderr.strip()[:2000]}")
        if result.stdout and result.stdout.strip():
            parts.append(f"stdout: {result.stdout.strip()[:1000]}")
        return "\n".join(parts)


def write_file_tool(relative_path: str, content: str, workspace_path: str) -> str:
    """
    Write a file into the workspace at `relative_path`.

    Args:
        relative_path: Path relative to workspace root (e.g. "src/App.jsx").
        content: Full file content (UTF-8).
        workspace_path: Absolute path to the project workspace.

    Returns:
        Confirmation string on success, or "ERROR: <message>" on failure.
    """
    result = sandbox_write_file(relative_path, content, workspace_path)
    if result["success"]:
        return f"Wrote {result['bytes_written']} bytes to {relative_path}"
    else:
        return f"ERROR: {result['error']}"


def delete_file_tool(relative_path: str, workspace_path: str) -> str:
    """
    Delete a file or directory inside the workspace at `relative_path`.

    Use "" or "." for relative_path to clear everything inside the
    workspace root (e.g. for a "delete all files in the project" step)
    without deleting the workspace directory itself.

    This is the safe alternative to shell 'rm' — 'rm' is intentionally
    excluded from ALLOWED_COMMANDS, so this tool exists specifically so
    steps like "delete all files" have a legitimate path to succeed
    instead of the replanner repeatedly retrying blocked shell commands.

    Args:
        relative_path: Path relative to workspace root, or "" / "." to
            clear the workspace root's contents.
        workspace_path: Absolute path to the project workspace.

    Returns:
        Confirmation string listing what was deleted on success, or
        "ERROR: <message>" on failure.
    """
    result = sandbox_delete_path(relative_path, workspace_path)
    if result["success"]:
        deleted = result["deleted"]
        if not deleted:
            return "Nothing to delete — workspace was already empty."
        return f"Deleted {len(deleted)} item(s): {', '.join(deleted)}"
    else:
        return f"ERROR: {result['error']}"


def start_dev_server_tool(command_str: str, workspace_path: str, port: int) -> str:
    """
    Start a dev server and return its URL or an error string.

    Args:
        command_str: Server start command, e.g. "npm run dev" or "python3 -m http.server 8080".
        workspace_path: Absolute path to the project workspace.
        port: Port the server is expected to listen on.

    Returns:
        "http://localhost:<port>" on success, or "ERROR: <message>" on failure.
    """
    result = start_dev_server(command_str, cwd=workspace_path, port=port)
    if result["success"]:
        return result["url"]
    else:
        parts = [f"ERROR: {result['error']}"]
        if result.get("stderr"):
            parts.append(f"stderr: {result['stderr'][:1000]}")
        return "\n".join(parts)


def ask_human(question: str) -> str:
    """
    Ask the human a question and return their response.
    
    This is a placeholder function that triggers an interrupt in the graph
    to pause execution and wait for human input. The actual interrupt handling
    is done in the approval_node, which calls this function's logic via
    the LangGraph interrupt mechanism.
    
    Args:
        question: The question to ask the human
        
    Returns:
        The human's response (this is handled via interrupt/resume in the graph)
    """
    # This function is called from nodes but the actual interrupt happens
    # in the approval_node or a dedicated ask_human_node
    # For now, return a placeholder - the real implementation uses interrupt()
    return f"[ASK_HUMAN: {question}]"


# ---------------------------------------------------------------------------
# Browser Automation Tool (browser-use + OpenRouter)
# ---------------------------------------------------------------------------

def browser_use_tool(
    action: str = "run_task",
    task: str = "",
    url: str = "",
    selector: str = "",
    value: str = "",
    credentials: dict = None,
    fields: dict = None,
    filter_actions: list = None,
    steps: list = None,
    checks: list = None,
    criteria: str = "cheapest",
    extract: str = "all visible text",
    save_path: str = None,
    direction: str = "down",
    amount: int = 500,
    timeout: float = None,
    sandbox_mode: bool = False,
) -> str:
    """
    Execute browser automation actions using browser-use with OpenRouter.
    Supports 16 distinct functionalities:
      1. Search + Compare on Booking Flow
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
     13. Explicit Action Primitives (navigate, click, fill, screenshot, etc.)
     14. Graceful Stuck-State Handling
     15. Human-in-the-Loop (HITL) Approval
     16. Sandboxed Execution

    Args:
        action: The browser action/primitive to execute (e.g. 'run_task', 'navigate', 'click', 'fill', 'login', 'scrape', etc.)
        task: Natural language task description or prompt
        url: Target web page URL
        selector: CSS selector or element description for targeted actions
        value: Input value for fill, select, etc.
        credentials: Dict with 'username', 'password', selectors, etc. for login
        fields: Dict of form field labels/selectors to values for form filling
        filter_actions: List of filter dicts for client-side filter interaction
        steps: List of step instructions for multi-step workflows
        checks: List of test validation dicts for site testing
        criteria: Comparison criteria ('cheapest', 'best match', etc.)
        extract: What information to extract during scraping
        save_path: File path to save screenshots
        direction: Scroll direction ('down', 'up')
        amount: Pixel distance to scroll
        timeout: Action timeout in seconds
        sandbox_mode: Run in hardened sandboxed mode

    Returns:
        JSON string representation of BrowserToolResult
    """
    from src.tools.browser_tool import get_browser_tool, _run_async

    tool = get_browser_tool(sandbox_mode=sandbox_mode)
    result = _run_async(
        tool.execute(
            action=action,
            task=task,
            url=url,
            selector=selector,
            value=value,
            credentials=credentials,
            fields=fields,
            filter_actions=filter_actions,
            steps=steps,
            checks=checks,
            criteria=criteria,
            extract=extract,
            save_path=save_path,
            direction=direction,
            amount=amount,
            timeout=timeout,
        )
    )
    return result.to_json()


def close_browser_session_tool() -> str:
    """Tear down active browser session at the end of a plan run."""
    from src.tools.browser_tool import close_browser_tool, _run_async
    _run_async(close_browser_tool())
    return "Browser session closed."

