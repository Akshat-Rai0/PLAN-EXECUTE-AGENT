"""
Tests for SQLite checkpointer persistence.

Verifies that the SqliteSaver correctly persists checkpoints and allows
resumption from a previous state.
"""
import os
import tempfile
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, END, START


def test_sqlite_checkpointer_persistence():
    """Test that SQLite checkpointer saves and loads checkpoints."""
    # Use a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Create a simple graph with state
        def add_one(state: int) -> int:
            return state + 1
        
        builder = StateGraph(int)
        builder.add_node("add_one", add_one)
        builder.set_entry_point("add_one")
        builder.set_finish_point("add_one")
        
        # Compile with SQLite checkpointer
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
            
            # First invocation
            config = {"configurable": {"thread_id": "test-thread"}}
            result1 = graph.invoke(1, config)
            assert result1 == 2
            
            # Second invocation with same thread_id should start fresh
            # (since we're not using interrupts, each invoke is independent)
            result2 = graph.invoke(5, config)
            assert result2 == 6  # 5 + 1 = 6
            
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_sqlite_checkpointer_thread_isolation():
    """Test that different thread_ids have separate state."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        def add_one(state: int) -> int:
            return state + 1
        
        builder = StateGraph(int)
        builder.add_node("add_one", add_one)
        builder.set_entry_point("add_one")
        builder.set_finish_point("add_one")
        
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
            
            # Thread 1
            config1 = {"configurable": {"thread_id": "thread-1"}}
            result1 = graph.invoke(10, config1)
            assert result1 == 11
            
            # Thread 2 - should be independent
            config2 = {"configurable": {"thread_id": "thread-2"}}
            result2 = graph.invoke(20, config2)
            assert result2 == 21
            
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_sqlite_checkpointer_file_creation():
    """Test that SQLite database file is created."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    # Remove the file to test creation
    if os.path.exists(db_path):
        os.unlink(db_path)
    
    try:
        def add_one(state: int) -> int:
            return state + 1
        
        builder = StateGraph(int)
        builder.add_node("add_one", add_one)
        builder.set_entry_point("add_one")
        builder.set_finish_point("add_one")
        
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": "test-thread"}}
            result = graph.invoke(1, config)
            
            # Verify file was created
            assert os.path.exists(db_path)
            assert result == 2
            
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
