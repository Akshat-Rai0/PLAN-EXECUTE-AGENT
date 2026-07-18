from tavily import TavilyClient
from dotenv import load_dotenv
import os
import re

from src.sandbox.shell_runner import run_shell_command, write_file as sandbox_write_file, ALLOWED_COMMANDS
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
