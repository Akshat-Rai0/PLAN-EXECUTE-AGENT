from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from .llm import get_llm



@tool
def breakdown_task(goal: str) -> str:
    """
    Break down a given task/goal into smaller, executable subtasks.
    
    This tool analyzes the goal and creates a step-by-step plan to achieve it.
    Each step should be actionable and clearly defined.
    
    Args:
        goal: The main task or goal to break down
        
    Returns:
        A formatted plan with numbered steps
    """
    
    llm = get_llm()
    
    prompt = f"""Role:
You are a task planning assistant that breaks down complex goals into actionable steps.

Task:
Analyze the given goal and create a step-by-step plan to achieve it.

Constraints:
- Break down the goal into 3-7 clear, actionable steps
- Each step should be specific and executable
- Steps should follow a logical sequence
- Use arrow notation (→) to show the flow
- Keep steps concise but descriptive

Goal:
{goal}

Output format:
Plan: step 1 → step 2 → step 3 → ..."""

    messages = [
        SystemMessage(content="You are a helpful task planning assistant."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    return response.content.strip()