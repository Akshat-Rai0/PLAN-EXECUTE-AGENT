"""
Tests for risk classification system.

Verifies that tools are correctly classified as HIGH or LOW risk.
"""
import pytest
from src.tools.risk_classifier import classify_tool_risk, RiskLevel


def test_high_risk_tools():
    """Test that HIGH-risk tools are correctly classified."""
    high_risk_tools = [
        "shell_command",
        "write_file",
        "file_editor",
        "code_executor",
        "start_server",
    ]
    
    for tool in high_risk_tools:
        risk = classify_tool_risk(tool)
        assert risk == RiskLevel.HIGH, f"{tool} should be HIGH risk"


def test_low_risk_tools():
    """Test that LOW-risk tools are correctly classified."""
    low_risk_tools = [
        "tavily_search",
        "web_search",
        "today_date",
        "reason",
        "setup_workspace",
    ]
    
    for tool in low_risk_tools:
        risk = classify_tool_risk(tool)
        assert risk == RiskLevel.LOW, f"{tool} should be LOW risk"


def test_unknown_tools_default_high():
    """Test that unknown tools default to HIGH risk for safety."""
    unknown_tools = [
        "unknown_tool",
        "custom_function",
        "arbitrary_command",
    ]
    
    for tool in unknown_tools:
        risk = classify_tool_risk(tool)
        assert risk == RiskLevel.HIGH, f"{tool} should default to HIGH risk"


def test_case_insensitive_classification():
    """Test that classification is case-insensitive."""
    assert classify_tool_risk("SHELL_COMMAND") == RiskLevel.HIGH
    assert classify_tool_risk("Shell_Command") == RiskLevel.HIGH
    assert classify_tool_risk("shell_command") == RiskLevel.HIGH
    
    assert classify_tool_risk("TAVILY_SEARCH") == RiskLevel.LOW
    assert classify_tool_risk("Tavily_Search") == RiskLevel.LOW
    assert classify_tool_risk("tavily_search") == RiskLevel.LOW


def test_whitespace_handling():
    """Test that whitespace is handled correctly."""
    assert classify_tool_risk(" shell_command ") == RiskLevel.HIGH
    assert classify_tool_risk("\ttavily_search\n") == RiskLevel.LOW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
