import os

node_code = """
def browser_node(state: State) -> dict:
    \"\"\"
    Execute a browser step using BrowserExecutor.
    \"\"\"
    plan = state["plan"]
    if plan is None:
        raise RuntimeError("browser_node called with no plan")
    current_step = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
    if current_step is None:
        raise RuntimeError("browser_node called with no RUNNING step")

    log_update = _log_approval(state, "browser", current_step.task)

    from src.executor.browser_executor import BrowserExecutor
    from src.models.browser_models import BrowserAction
    import json
    
    executor = BrowserExecutor()
    try:
        # Get initial state
        compressed_state = executor.execute(BrowserAction(action="wait", value="0"))
        
        system_prompt = "You are a web browsing agent. Decide the next action. Output a valid JSON with 'action', and optionally 'target' (integer ID) and 'value' (string). Actions: goto, click, type, select, check, upload, scroll, wait, finish."
        llm = get_llm()
        
        max_steps = 15
        for _ in range(max_steps):
            prompt = f"Goal: {plan.goal}\\nStep Task: {current_step.task}\\n\\nCurrent Page State:\\n{compressed_state}\\n\\nWhat is the next BrowserAction? Output ONLY JSON."
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ]
            response = llm.invoke(messages)
            content = response.content.strip()
            
            if content.startswith("```"):
                content = "\\n".join([line for line in content.splitlines() if not line.startswith("```")]).strip()
                
            try:
                data = json.loads(content)
                action = BrowserAction(**data)
            except Exception as e:
                print(f"❌ Failed to parse browser action: {content}. Error: {e}")
                action = BrowserAction(action="wait", value="2")
                
            print(f"🌐 Browser Action: {action.action} target={action.target} value={action.value}")
            
            if action.action.lower() == "finish":
                current_step.status = StepStatus.DONE
                current_step.result = "Browser task finished. Final state:\\n" + compressed_state
                break
                
            compressed_state = executor.execute(action)
            
        else:
            current_step.status = StepStatus.FAILED
            current_step.error = f"Browser loop exceeded {max_steps} steps."
            current_step.result = "Browser loop timed out."
            
    except Exception as e:
        current_step.status = StepStatus.FAILED
        current_step.error = str(e)
        current_step.result = str(e)
    finally:
        executor.close()
        
    return {"plan": plan, "steps_executed": 1, **log_update}
"""

with open("src/agents/plan_execute/nodes.py", "a") as f:
    f.write("\n" + node_code + "\n")
