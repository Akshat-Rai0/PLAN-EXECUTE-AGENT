"""
Risk classification for tool operations.

HIGH-risk tools can cause significant damage if misused (file system changes,
code execution, network services). LOW-risk tools are read-only or purely
informational.
"""

from enum import Enum
from typing import Literal


class RiskLevel(str, Enum):
    """Risk level classification for tool operations."""
    LOW = "LOW"
    HIGH = "HIGH"


HIGH_RISK_TOOLS = {
    "shell_command",      # Can execute arbitrary commands
    "write_file",         # Can write arbitrary files
    "file_editor",        # Can write arbitrary files
    "delete_file",        # Destructive — deletes files/directories in the workspace
    "code_executor",      # Can execute arbitrary Python code
    "start_server",       # Can start network services
}

LOW_RISK_TOOLS = {
    "tavily_search",      # Read-only web search
    "web_search",         # Read-only web search
    "today_date",         # System date read
    "reason",             # Pure LLM reasoning
    "setup_workspace",    # Directory creation only (limited scope)
}


def classify_tool_risk(tool_hint: str) -> RiskLevel:
    """
    Classify a tool's risk level based on its tool_hint.

    Args:
        tool_hint: The tool hint from a step (e.g., "shell_command", "tavily_search")

    Returns:
        RiskLevel.HIGH for dangerous operations, RiskLevel.LOW for safe operations
    """
    tool_hint_normalized = tool_hint.lower().strip()
    
    if tool_hint_normalized in HIGH_RISK_TOOLS:
        return RiskLevel.HIGH
    elif tool_hint_normalized in LOW_RISK_TOOLS:
        return RiskLevel.LOW
    else:
        # Unknown tools default to HIGH for safety
        return RiskLevel.HIGH
