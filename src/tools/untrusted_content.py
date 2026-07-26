"""
Untrusted content handling for web-extracted data.

Provides injection detection and XML wrapping for web content to prevent
prompt injection attacks when LLMs process scraped web data.
"""

import re
from typing import List


def wrap_web_content(text: str, source_url: str) -> str:
    """
    Wrap page-derived text in XML tags to mark it as untrusted.

    Args:
        text: The web content to wrap
        source_url: The URL where the content originated

    Returns:
        XML-wrapped string with source attribution
    """
    return f'<untrusted_web_content source="{source_url}">\n{text}\n</untrusted_web_content>'


def scan_for_injection(text: str) -> bool:
    """
    Heuristic scan for prompt injection patterns in web content.

    Uses imperative-pattern heuristics to detect common injection attempts:
    - Instructions to ignore previous context
    - Role override attempts
    - System prompt manipulation
    - Command injection patterns

    Args:
        text: The content to scan

    Returns:
        True if injection patterns are detected, False otherwise
    """
    if not text:
        return False

    text_lower = text.lower()

    # Pattern 1: Ignore previous instructions
    ignore_patterns = [
        r"ignore\s+(all\s+)?previous\s+(instructions|commands|prompts)",
        r"disregard\s+(everything\s+)?above",
        r"forget\s+(everything\s+)?(i\s+)?told\s+you",
        r"don'?t\s+listen\s+to\s+(the\s+)?(previous|earlier)\s+(instructions|prompts)",
    ]

    # Pattern 2: Role override / new persona
    role_patterns = [
        r"you\s+are\s+now\s+(a\s+)?(new\s+)?",
        r"act\s+as\s+(if\s+you\s+are\s+)?",
        r"pretend\s+to\s+be\s+(a\s+)?",
        r"your\s+new\s+(role|persona|identity)\s+is",
        r"switch\s+to\s+(a\s+)?(new\s+)?(role|persona)",
    ]

    # Pattern 3: System prompt manipulation
    system_patterns = [
        r"override\s+(your\s+)?(system\s+)?prompt",
        r"change\s+(your\s+)?(system\s+)?instructions",
        r"replace\s+(your\s+)?programming",
        r"modify\s+(your\s+)?(core\s+)?instructions",
        r"update\s+(your\s+)?(system\s+)?message",
    ]

    # Pattern 4: Command injection
    command_patterns = [
        r"execute\s+(this\s+)?(command|instruction)",
        r"run\s+(this\s+)?(code|script)",
        r"perform\s+(the\s+)?following\s+(action|task)",
        r"carry\s+out\s+(this\s+)?(order|command)",
    ]

    # Pattern 5: Output formatting manipulation
    output_patterns = [
        r"output\s+(only\s+)?(the\s+)?(following|this)",
        r"print\s+(exactly\s+)?(the\s+)?following",
        r"respond\s+(only\s+)?with",
        r"return\s+(nothing\s+)?(but\s+)?(the\s+)?following",
    ]

    # Pattern 6: Context boundary breaking
    context_patterns = [
        r"above\s+(is\s+)?(context|information)",
        r"below\s+(is\s+)?(context|information)",
        r"here\s+(is\s+)?(the\s+)?(context|data)",
        r"use\s+(the\s+)?(following\s+)?(context|information)",
    ]

    all_patterns = (
        ignore_patterns + role_patterns + system_patterns +
        command_patterns + output_patterns + context_patterns
    )

    for pattern in all_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    return False
