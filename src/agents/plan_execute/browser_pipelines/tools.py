"""
Custom tools registry for browser pipelines.

Provides domain-specific actions that extend browser-use agent capabilities.
Integrates with browser-use Tools class pattern.
"""
import asyncio
import json
from typing import Any, Optional, Callable
from pydantic import BaseModel, Field

try:
    from browser_use.tools.service import Tools
    from browser_use.agent.views import ActionResult
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    # Create a fallback Tools class if browser-use isn't available
    class Tools:
        def __init__(self, exclude_actions: Optional[list[str]] = None, output_model: Optional[type] = None):
            self.exclude_actions = exclude_actions or []
            self.output_model = output_model
            self._registry = {}
        
        def action(self, name: str, param_model: Optional[type] = None):
            def decorator(func: Callable):
                self._registry[name] = func
                return func
            return decorator
        
        @property
        def registry(self):
            return self._registry
    
    class ActionResult:
        def __init__(self, extracted_content: str = "", include_in_memory: bool = False):
            self.extracted_content = extracted_content
            self.include_in_memory = include_in_memory


# Custom Action Models
class WebpageLink(BaseModel):
    """Model for webpage link action."""
    link: str = Field(..., description="URL to navigate to")


class SearchQuery(BaseModel):
    """Model for search action."""
    query: str = Field(..., description="Search query string")


class ExtractDataRequest(BaseModel):
    """Model for structured data extraction."""
    extraction_goal: str = Field(..., description="What data to extract")
    schema_hint: Optional[str] = Field(default=None, description="Hint about expected schema")


class CustomToolsRegistry:
    """
    Registry for custom browser pipeline tools.
    
    Provides domain-specific actions that can be used with browser-use agents.
    Maintains compatibility with existing BrowserTool primitives.
    """
    
    def __init__(self):
        self._tools = Tools()
        self._custom_actions = {}
        self._browser_tool = None
    
    def set_browser_tool(self, browser_tool):
        """Set the BrowserTool instance for actions to use."""
        self._browser_tool = browser_tool
    
    def register_action(self, name: str, param_model: Optional[type] = None):
        """
        Decorator to register a custom action.
        
        Args:
            name: Name of the action
            param_model: Pydantic model for action parameters
        """
        def decorator(func: Callable):
            # Register with browser-use Tools if available
            if BROWSER_USE_AVAILABLE:
                self._tools.action(name, param_model)(func)
            # Also keep our own registry
            self._custom_actions[name] = {
                'func': func,
                'param_model': param_model
            }
            return func
        return decorator
    
    def get_tools(self) -> Tools:
        """Get the browser-use Tools instance."""
        return self._tools
    
    def get_action(self, name: str) -> Optional[Callable]:
        """Get a custom action by name."""
        action = self._custom_actions.get(name)
        return action['func'] if action else None
    
    def list_actions(self) -> list[str]:
        """List all registered custom actions."""
        return list(self._custom_actions.keys())


# Global registry instance
_global_registry = CustomToolsRegistry()


def get_custom_tools_registry() -> CustomToolsRegistry:
    """Get the global custom tools registry."""
    return _global_registry


# Example custom actions
@_global_registry.register_action("go_to_webpage", WebpageLink)
async def go_to_webpage(webpage_info: WebpageLink) -> ActionResult:
    """
    Navigate to a specific webpage.
    
    Args:
        webpage_info: WebpageLink model with URL
    
    Returns:
        ActionResult with navigation status
    """
    registry = get_custom_tools_registry()
    if registry._browser_tool:
        result = await registry._browser_tool.navigate(webpage_info.link)
        return ActionResult(
            extracted_content=f"Navigated to {webpage_info.link}",
            include_in_memory=True
        )
    return ActionResult(
        extracted_content=f"Would navigate to {webpage_info.link}",
        include_in_memory=True
    )


@_global_registry.register_action("search_web", SearchQuery)
async def search_web(search_query: SearchQuery) -> ActionResult:
    """
    Perform a web search for the given query.
    
    Args:
        search_query: SearchQuery model with search string
    
    Returns:
        ActionResult with search results
    """
    # This would integrate with a search API (e.g., Tavily, Google)
    # For now, return a placeholder
    results = {
        "query": search_query.query,
        "results": [
            {"title": f"Result for {search_query.query}", "url": "https://example.com"}
        ]
    }
    return ActionResult(
        extracted_content=json.dumps(results, indent=2),
        include_in_memory=True
    )


@_global_registry.register_action("extract_structured_data", ExtractDataRequest)
async def extract_structured_data(request: ExtractDataRequest) -> ActionResult:
    """
    Extract structured data from the current page based on a goal.
    
    Args:
        request: ExtractDataRequest with extraction goal and schema hint
    
    Returns:
        ActionResult with extracted structured data
    """
    registry = get_custom_tools_registry()
    if registry._browser_tool:
        prompt = f"Extract the following structured data from this page: {request.extraction_goal}"
        if request.schema_hint:
            prompt += f"\nExpected schema: {request.schema_hint}"
        
        result = await registry._browser_tool.run_task(task=prompt, max_steps=3)
        if result.success:
            return ActionResult(
                extracted_content=result.extracted_text or "No data extracted",
                include_in_memory=True
            )
    
    return ActionResult(
        extracted_content="No browser tool available for extraction",
        include_in_memory=False
    )


def create_pipeline_tools(browser_tool=None) -> Tools:
    """
    Create a Tools instance with custom actions for a pipeline.
    
    Args:
        browser_tool: Optional BrowserTool instance for actions to use
    
    Returns:
        Tools instance with registered custom actions
    """
    registry = get_custom_tools_registry()
    if browser_tool:
        registry.set_browser_tool(browser_tool)
    return registry.get_tools()
