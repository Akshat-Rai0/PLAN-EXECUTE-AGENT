"""Patchable dependencies re-exported by the nodes package for tests.

Submodules resolve these through ``_pkg()`` at runtime so
``patch('src.agents.plan_execute.nodes.tavily_search')`` keeps working.
"""

from ..llm import get_llm, get_cheap_llm
from ..tools import breakdown_task, bound_replan_context
from src.tools.registry import tavily_search, today_date
from src.tools.browser_use import run_browser_task_sync
from src.sandbox.runner import run_in_sandbox
from src.synthesis.codegen import declare_schema, generate_function_code
from src.synthesis.validator import validate_synthesized_function
