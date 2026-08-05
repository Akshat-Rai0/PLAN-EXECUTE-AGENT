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

    WHEN TO USE:
    - When you need current information from the internet (news, facts, data)
    - When the answer isn't known or requires verification from external sources
    - When you need specific details about people, events, products, or topics
    - As the FIRST choice for information gathering before considering other tools

    WHEN NOT TO USE:
    - For pure reasoning or analysis of existing information (use reason/none)
    - For calculations or data processing (use code_executor)
    - When you already have the needed information in context
    - For rendered page interaction or form filling (use browser_use)

    EXAMPLES:
    - "Search for the current CEO of Microsoft"
    - "Find the population of Tokyo according to 2024 census data"
    - "Look up the latest Python version release date"
    - "Search for reviews of the iPhone 15 Pro camera quality"

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
    """
    Return today's date in YYYY-MM-DD format.

    WHEN TO USE:
    - When the goal explicitly asks for today's date or current date
    - When you need to anchor time-sensitive queries to the current date
    - When processing recency-sensitive information that needs a date reference
    - Automatically injected for goals containing recency language ("latest", "recent", "current")

    WHEN NOT TO USE:
    - When you need date calculations or manipulation (use code_executor)
    - When you need historical dates or date ranges (use search)
    - When the task doesn't involve time-sensitive information

    EXAMPLES:
    - "What's today's date?" → Direct call returns "2026-08-05"
    - "Who won the World Cup this year?" → Date anchor prepended before search
    - "What are the latest stock prices?" → Date anchor ensures current data
    - "Find recent Python job postings" → Date anchor for recency filtering

    Returns:
        Today's date in YYYY-MM-DD format (e.g., "2026-08-05")
    """
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Coding-agent tools — shell, file I/O, dev server
# ---------------------------------------------------------------------------

def shell_command_tool(command: str, workspace_path: str) -> str:
    """
    Run a shell command inside the agent workspace and return stdout or an
    error string. Wraps shell_runner.run_shell_command.

    WHEN TO USE:
    - For development commands: npm install, pip install, git operations
    - For project scaffolding: npx create-vite, cargo init, go mod init
    - For build processes: npm run build, make, cargo build
    - For package management: npm, pip, cargo, yarn, composer
    - For version control: git clone, git checkout, git branch
    - For directory operations: mkdir, ls (when not using dedicated file tools)

    WHEN NOT TO USE:
    - For file deletion (use delete_file_tool - rm is blocked for safety)
    - For writing/reading files (use write_file_tool instead)
    - For starting dev servers (use start_dev_server_tool instead)
    - For arbitrary system commands or administrative tasks (safety restriction)
    - For commands requiring user input (non-interactive execution only)

    EXAMPLES:
    - "npm install" → Install dependencies from package.json
    - "npx create-vite@latest my-app -- --template react" → Scaffold React app
    - "git clone https://github.com/user/repo.git" → Clone repository
    - "pip install -r requirements.txt" → Install Python dependencies
    - "ls -la" → List directory contents (when needed for exploration)
    - "mkdir -p src/components" → Create directory structure

    SAFETY NOTES:
    - 'rm' command is intentionally blocked - use delete_file_tool instead
    - Commands run in sandboxed environment with timeout and memory limits
    - Network access is restricted to allowlisted domains only
    - Commands requiring user input will fail (non-interactive execution)

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

    WHEN TO USE:
    - Creating or editing source code files (JS, Python, HTML, CSS, etc.)
    - Writing configuration files (package.json, tsconfig.json, .env files)
    - Creating documentation files (README.md, docs, comments)
    - Writing test files or specification files
    - Creating data files (JSON, CSV, XML, etc.)
    - After project scaffolding when implementing features

    WHEN NOT TO USE:
    - For file deletion (use delete_file_tool instead)
    - For reading file contents (no dedicated read tool - use code_executor if needed)
    - For appending to existing files (rewrite entire content instead)
    - For binary files (text-based content only)

    EXAMPLES:
    - Write source code: "src/App.jsx" with React component code
    - Configuration: "package.json" with project dependencies
    - Documentation: "README.md" with project description
    - Styles: "src/styles.css" with CSS rules
    - Config: ".env.example" with environment variable templates
    - Tests: "tests/app.test.js" with test cases

    WORKFLOW NOTES:
    - Automatically creates parent directories if they don't exist
    - Overwrites existing files entirely (no append mode)
    - Content should be complete file content, not partial updates
    - Use after setup_workspace tool for project structure
    - Typically followed by shell_command_tool for package installation

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

    WHEN TO USE:
    - Cleaning up generated files or temporary artifacts
    - Removing outdated configuration files
    - Deleting specific source files during refactoring
    - Clearing workspace contents for fresh start
    - Removing build artifacts (node_modules, dist, build directories)
    - ANY deletion task - never use shell 'rm' command

    WHEN NOT TO USE:
    - For reading file contents (use code_executor if needed)
    - For moving/renaming files (delete and recreate instead)
    - For operations outside the workspace (workspace-scoped only)
    - When uncertain about file contents (destructive operation)

    EXAMPLES:
    - Delete specific file: "old_config.json" → Removes single file
    - Delete directory: "node_modules/" → Removes entire directory tree
    - Clear workspace: "" or "." → Deletes all workspace contents
    - Remove build artifacts: "dist/" → Deletes build output directory
    - Clean up: "*.tmp" → Deletes files matching pattern (if supported)
    - Remove cache: ".cache/" → Deletes cache directory

    SAFETY NOTES:
    - This is the ONLY safe way to delete files in the agent
    - Shell 'rm' command is intentionally blocked for security
    - Operation is irreversible - use with caution
    - Workspace-scoped only - cannot delete files outside workspace
    - Empty string "" clears entire workspace contents

    SPECIAL USAGE:
    - Use "" or "." for relative_path to clear everything inside the
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

    WHEN TO USE:
    - Starting web development servers (React, Vue, Angular dev servers)
    - Running backend API servers (Flask, Django, Express dev servers)
    - Starting static file servers (python http.server, live-server)
    - Launching database servers for local development
    - Running development environments that need HTTP access
    - As the FINAL step in app-building workflows

    WHEN NOT TO USE:
    - For production deployments (dev servers only)
    - For one-off command execution (use shell_command_tool instead)
    - For servers that don't need HTTP access (use shell_command_tool)
    - For long-running background processes (dev servers only)
    - When server startup isn't the goal of the task

    EXAMPLES:
    - React dev server: "npm run dev" on port 5173
    - Python HTTP server: "python3 -m http.server 8000" on port 8000
    - Flask dev server: "flask run --port 5000" on port 5000
    - Vite dev server: "npm run dev" on port 3000
    - Express dev server: "node server.js" on port 8080
    - Django dev server: "python manage.py runserver" on port 8000

    WORKFLOW NOTES:
    - Typically used as the LAST step after scaffolding and file creation
    - Server runs in background with timeout and port detection
    - Returns localhost URL for manual testing or verification
    - Process is killed after timeout or when agent completes
    - Should follow shell_command_tool for dependency installation

    TECHNICAL DETAILS:
    - Non-blocking execution with port-open detection
    - Timeout-based process management (prevents hanging)
    - Stderr capture for error diagnostics
    - Process cleanup on completion or failure
    - Network access restrictions still apply

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

