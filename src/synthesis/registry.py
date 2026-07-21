"""
Registry for synthesized tools.

Provides a singleton registry that tracks validated synthesized tools
across plan execution, enabling reuse of capabilities without re-synthesis.
"""

from typing import Optional, Dict
from .schema import SynthesizedTool


class SynthesisRegistry:
    """
    Thread-safe registry for synthesized tools.
    
    Tools are only registered after passing sandbox validation, ensuring
    that anything in the registry is trusted to execute. The registry
    tracks usage counts and provides lookup by capability name.
    """
    
    def __init__(self):
        self._tools: Dict[str, SynthesizedTool] = {}
    
    def register(self, tool: SynthesizedTool) -> None:
        """Register a validated synthesized tool."""
        self._tools[tool.capability_name] = tool
    
    def get(self, capability_name: str) -> Optional[SynthesizedTool]:
        """Retrieve a tool by capability name, if registered."""
        return self._tools.get(capability_name)
    
    def has(self, capability_name: str) -> bool:
        """Check if a tool is registered by capability name."""
        return capability_name in self._tools
    
    def mark_used(self, capability_name: str) -> None:
        """Increment usage counter for a registered tool."""
        if capability_name in self._tools:
            self._tools[capability_name].times_used += 1
    
    def list_all(self) -> Dict[str, SynthesizedTool]:
        """Return all registered tools."""
        return self._tools.copy()
    
    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)


# Singleton instance for use across the application
default_registry = SynthesisRegistry()
