
import sys
import os
import json

# When running directly, add parent directories to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir)

# Now use absolute imports
from src.agents.plan_execute.state import State
from src.agents.plan_execute.graph import build_graph

def main():
    """Main CLI entry point for plan generation."""
    
    # Get input from command line argument or prompt
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = input("Enter your task: ")
    
    if not user_input.strip():
        print("Error: No input provided")
        sys.exit(1)
    
    print(f"\n🎯 Input: {user_input}")
    print("⏳ Generating plan...\n")
    
    # Build the graph
    graph = build_graph()
    
    # Create initial state
    initial_state: State = {
        "input": user_input,
        "plan": None,
        "output": ""
    }
    
    # Invoke the graph with required config
    config = {"configurable": {"thread_id": "cli-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Display the result
    print("✅ Plan Generated:")
    print("-" * 50)
    
    # Handle Plan object (Pydantic model)
    plan = result["plan"]
    if hasattr(plan, 'model_dump_json'):
        # It's a Pydantic model
        plan_json = plan.model_dump_json(indent=2)
        print(plan_json)
        
        # Save to file
        output_dir = os.path.join(grandparent_dir, "plans")
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename based on goal (sanitized)
        safe_goal = "".join(c for c in user_input if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_goal = safe_goal.replace(' ', '_')[:50]  # Limit length
        filename = f"{safe_goal}_plan.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w') as f:
            f.write(plan_json)
        
        print(f"\n💾 Plan saved to: {filepath}")
    else:
        # Fallback for string/other types
        print(str(plan))
    
    print("-" * 50)


if __name__ == "__main__":
    main()
