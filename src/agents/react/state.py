
from enum import Enum
from typing import Optional, TypedDict, Annotated
from pydantic import BaseModel
from typing_extensions import TypedDict as ExtTypedDict
from operator import add

# Import the reducer from plan_execute
from src.agents.plan_execute.state import sum_replan_count

MAX_REACT_ITERATIONS = 15

class Turn(BaseModel):
    thought: str
    action: str            # tool name, or "final_answer"
    action_input: str      # the query/argument passed to the tool
    observation: Optional[str] = None   # filled in after the tool runs

class ReactState(TypedDict):
    goal: str
    history: Annotated[list[Turn], add]   # append-only, use operator.add as reducer
    final_answer: Optional[str]
    iterations: Annotated[int, sum_replan_count]  # reuse your existing accumulating reducer