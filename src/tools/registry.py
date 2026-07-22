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
# Browser automation tool
# ---------------------------------------------------------------------------

def browser_use_tool(task: str, headless: bool = True, timeout_seconds: float = 120.0) -> str:
    """
    Execute a browser automation task using the browser-use library with Groq LLM.

    This function creates a browser-use Agent configured with Groq's native
    ChatGroq wrapper (browser_use.llm.ChatGroq — NOT a hand-rolled adapter,
    see note below), executes the specified task (form filling, data
    extraction, navigation, etc.), and returns the results including actions
    taken and extracted data.

    Args:
        task: The browser automation task description (e.g., "fill out the
            contact form on example.com").
        headless: Whether to run the browser in headless mode (True, no
            visible window) or headed mode (False, visible window — useful
            for debugging).
        timeout_seconds: Hard wall-clock cap on the entire browser-use run.
            Without this, a stuck agent.run() call blocks the whole
            LangGraph node — and therefore the whole CLI process —
            indefinitely with zero progress output, which is
            indistinguishable from a genuine hang. This was the actual
            root cause of a real "opens a browser, then no progress"
            report: the previous hand-rolled LLM wrapper below returned
            objects browser-use's internal agent loop couldn't parse into
            an action, causing it to retry/stall silently rather than
            raising a clean, catchable error.

    Returns:
        A string containing the agent's result including actions performed
        and any extracted data, an ERROR string on failure, or a TIMEOUT
        string if the run exceeded timeout_seconds without completing.
    """
    try:
        # Defensive backstop for the same extension-download bug the
        # explicit enable_default_extensions=False below already handles
        # via BrowserProfile — set this BEFORE importing/using browser_use
        # in case any other internal code path reads browser-use's own
        # global CONFIG default rather than the specific BrowserProfile
        # instance constructed further down. Belt-and-suspenders: the
        # BrowserProfile kwarg is the primary fix (confirmed to work),
        # this env var is a backstop, not required for the fix to work.
        os.environ.setdefault("BROWSER_USE_DISABLE_EXTENSIONS", "1")

        from browser_use import Agent, BrowserProfile
        from browser_use.llm import ChatGroq
        import asyncio

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return "ERROR: GROQ_API_KEY not found in environment variables"

        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        # Use browser-use's OWN native ChatGroq wrapper (browser_use.llm.ChatGroq),
        # not a hand-rolled adapter. browser-use's BaseChatModel interface
        # requires an async ainvoke(messages, output_format=...) method that
        # returns a ChatInvokeCompletion object — the library uses this for
        # STRUCTURED output (it asks the LLM to select a specific action
        # schema on every step). A bare chat-completions wrapper that
        # returns a plain AIMessage does not satisfy this contract; the
        # previous implementation's SimpleLLM class had the wrong ainvoke
        # signature entirely (no output_format parameter, wrong return
        # type), which is the most likely reason browser-use's internal
        # agent loop never made forward progress — it never lets an
        # exception surface, it just can't parse what comes back and keeps
        # trying. browser-use ships this wrapper specifically so callers
        # don't need to hand-write one; verified present in browser-use
        # 0.13.6's public API (browser_use.llm.ChatGroq).
        llm = ChatGroq(
            model=groq_model,
            api_key=groq_api_key,
            timeout=60,       # per-LLM-call timeout, distinct from the
                               # overall run timeout below
            max_retries=2,
        )

        # headless lives on BrowserProfile, not on Agent directly — the
        # previous implementation accepted a headless parameter but never
        # passed it anywhere, so browser-use fell back to its own default
        # (effectively headed / auto-detected), which is why a visible
        # Chrome window opened even though headless=True was the caller's
        # intent.
        # Disable browser-use's default extensions (uBlock Origin, cookie
        # handler, URL cleaner). This works around a real bug in
        # browser-use 0.13.6 itself: BrowserProfile._download_extension()
        # calls urllib.request.urlopen(url) with NO timeout at all, and
        # it's a plain synchronous blocking call (not wrapped in
        # loop.run_in_executor or similar) invoked while building Chrome's
        # launch args — i.e. inside the async agent.run() path, but not
        # itself async. Verified experimentally (not assumed): a blocking
        # call with no internal awaits, run directly inside an async
        # function, freezes the ENTIRE event loop — asyncio.wait_for's
        # timeout (see below) literally cannot interrupt it, because the
        # timeout mechanism itself depends on the event loop getting
        # control back at an await point, which never happens here. If
        # the extension download stalls (slow network, blocked/filtered
        # domain, DNS issue — all plausible in a sandboxed/CI/headless
        # environment), the whole process hangs with the timeout below
        # never firing. This exact symptom was reproduced from a real run
        # (log showed "Downloading uBlock Origin Lite extension..." with
        # no further output). These extensions are non-essential for
        # scripted automation tasks, so disabling them sidesteps the bug
        # entirely rather than trying to work around a genuinely
        # un-interruptible blocking call from the outside.
        browser_profile = BrowserProfile(headless=headless, enable_default_extensions=False)

        agent = Agent(
            task=task,
            llm=llm,
            browser_profile=browser_profile,
        )

        # Hard timeout around the whole run. Without this, a stuck
        # agent.run() blocks this LangGraph node (and therefore the whole
        # CLI process) forever with no progress output — exactly the
        # symptom reported ("browser opens, then no progress"). This does
        # NOT fix a slow-but-working run; it turns a silent, indefinite
        # hang into a clear, actionable failure the replanner can react to.
        try:
            result = asyncio.run(asyncio.wait_for(agent.run(), timeout=timeout_seconds))
        except asyncio.TimeoutError:
            return (
                f"ERROR: Browser automation timed out after {timeout_seconds}s "
                f"with no result. Task: {task!r}. This usually means the "
                "agent's internal loop got stuck (e.g. couldn't find a way "
                "to progress on the page, or hit a state it couldn't parse) "
                "rather than the page itself being slow to load."
            )

        # Extract and format the result. browser-use's AgentHistoryList
        # (what agent.run() returns) exposes final_result() as a METHOD,
        # not an attribute — calling it without parens on a real run would
        # return the bound method object itself, not the actual result
        # text, silently producing a useless "Result:
        # <bound method ...>" output instead of a real error.
        if hasattr(result, "final_result") and callable(getattr(result, "final_result")):
            output = result.final_result()
        elif hasattr(result, "final_result"):
            output = result.final_result
        elif isinstance(result, list) and len(result) > 0:
            output = "\n".join(str(step) for step in result)
        else:
            output = str(result)

        if not output or not str(output).strip():
            return (
                f"ERROR: Browser automation completed without error but "
                f"produced no extractable result. Task: {task!r}. The run "
                "may have finished on an intermediate page rather than "
                "completing the task — check the task description is "
                "specific enough (e.g. 'report the title of the #1 post', "
                "not just 'go to the site')."
            )

        return f"Browser automation completed successfully.\n\nTask: {task}\n\nResult:\n{output}"

    except ImportError as e:
        return f"ERROR: Failed to import browser-use library: {e}. Ensure browser-use is installed: pip install browser-use"
    except Exception as e:
        return f"ERROR: Browser automation failed: {type(e).__name__}: {e}"
