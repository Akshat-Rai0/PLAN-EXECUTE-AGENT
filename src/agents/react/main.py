import sys
import os
import json
from datetime import datetime

# When running directly, add parent directories to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grandparent_dir)

# Now use absolute imports
from src.agents.react.state import ReactState
from src.agents.react.graph import build_react_graph


def main():
    """Main CLI entry point for ReAct agent."""
    
    # Get input from command line argument or prompt
    if len(sys.argv) > 1:
        goal = " ".join(sys.argv[1:])
    else:
        goal = input("Enter your goal: ")
    
    if not goal.strip():
        print("Error: No input provided")
        sys.exit(1)
    
    print(f"🎯 Goal: {goal}")
    print("⏳ Running ReAct agent...")
    print()
    
    # Build the graph
    graph = build_react_graph()
    
    # Create initial state
    initial_state: ReactState = {
        "goal": goal,
        "history": [],
        "final_answer": None,
        "iterations": 0
    }
    
    # Invoke the graph with required config
    config = {"configurable": {"thread_id": "react-cli-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Display the result
    print("✅ Execution Complete:")
    print("=" * 80)
    print()
    
    # Show turn history
    print("📝 Turn History:")
    print()
    for i, turn in enumerate(result["history"], 1):
        print(f"Turn {i}:")
        print(f"  Thought: {turn.thought}")
        print(f"  Action: {turn.action}")
        print(f"  Action Input: {turn.action_input}")
        print(f"  Observation: {turn.observation}")
        print()
    
    print("=" * 80)
    print()
    
    # Show final answer
    print("🧾 Final Answer:")
    print("=" * 80)
    print(result.get("final_answer", "No final answer generated"))
    print("=" * 80)
    print()
    
    # Show metrics
    print("📊 Metrics:")
    print(f"- Total iterations (LLM calls): {result['iterations']}")
    print("=" * 80)
    
    # Save result to JSON
    output_dir = os.path.join(grandparent_dir, "plans")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"react_result_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Convert turns to dict for JSON serialization
    result_data = {
        "goal": goal,
        "final_answer": result.get("final_answer"),
        "iterations": result["iterations"],
        "history": [
            {
                "thought": turn.thought,
                "action": turn.action,
                "action_input": turn.action_input,
                "observation": turn.observation
            }
            for turn in result["history"]
        ]
    }
    
    with open(filepath, 'w') as f:
        json.dump(result_data, f, indent=2)
    
    print(f"\n💾 Result saved to: {filepath}")


if __name__ == "__main__":
    main()
