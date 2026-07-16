
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
        "replan_count": 0,
        "consecutive_identical_replans": 0,
    }
    
    # Invoke the graph with required config
    config = {"configurable": {"thread_id": "cli-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Display the result
    print("✅ Execution Complete:")
    print("=" * 80)
    
    # Handle Plan object (Pydantic model)
    plan = result["plan"]
    if hasattr(plan, 'model_dump_json'):
        # It's a Pydantic model
        print(f"\n📋 Goal: {plan.goal}")
        print(f"\n📝 Steps Executed:")
        
        # Display each step with detailed information
        for step in plan.subtasks:
            print(f"\n  Step {step.id}: {step.task}")
            print(f"  └─ Tool: {step.tool_hint}")
            print(f"  └─ Status: {step.status}")
            
            if step.result:
                print(f"  └─ Result:")
                # Indent the result for better readability
                for line in step.result.split('\n'):
                    print(f"     {line}")
            
            if step.error:
                print(f"  └─ Error: {step.error}")

        # Display cancelled steps separately
        if plan.cancelled_steps:
            print(f"\n❌ Cancelled Steps (never executed):")
            for step in plan.cancelled_steps:
                print(f"\n  Step {step.id}: {step.task}")
                print(f"  └─ Reason: {step.error}")

        # Print the LLM-synthesized final answer explicitly. This is distinct
        # from any individual step's raw result — previously the CLI never
        # surfaced this at all, so what looked like "the final answer" was
        # actually just whichever step happened to run last.
        print(f"\n{'=' * 80}")
        print("🧾 Final Answer:")
        print("=" * 80)
        if plan.final_answer:
            print(plan.final_answer)
        else:
            print("(No synthesized final answer was produced for this run.)")

        # Save to file
        output_dir = os.path.join(grandparent_dir, "plans")
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename based on goal (sanitized)
        safe_goal = "".join(c for c in user_input if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_goal = safe_goal.replace(' ', '_')[:50]  # Limit length
        filename = f"{safe_goal}_plan.json"
        filepath = os.path.join(output_dir, filename)
        
        plan_json = plan.model_dump_json(indent=2)
        with open(filepath, 'w') as f:
            f.write(plan_json)
        
        print(f"\n💾 Plan saved to: {filepath}")
    else:
        # Fallback for string/other types
        print(str(plan))
    
    print("=" * 80)


if __name__ == "__main__":
    main()
