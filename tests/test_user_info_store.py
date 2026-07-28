"""
Tests for user information persistence store.
"""

import pytest
import tempfile
import json
from pathlib import Path
from src.tools.user_info_store import (
    UserInfoEntry,
    UserInfoStore,
    get_store_path,
    load_user_info_store,
    save_user_info_store,
    get_user_info_store,
    reset_user_info_store,
)


class TestUserInfoEntry:
    """Test UserInfoEntry model."""

    def test_create_entry(self):
        """Test creating a user info entry."""
        entry = UserInfoEntry(value="john@example.com", source="user_input")
        assert entry.value == "john@example.com"
        assert entry.source == "user_input"
        assert entry.confidence == 1.0
        assert entry.last_updated is not None

    def test_entry_serialization(self):
        """Test entry can be serialized to dict."""
        entry = UserInfoEntry(value="John Doe", source="conversation", confidence=0.9)
        data = entry.model_dump()
        assert data["value"] == "John Doe"
        assert data["source"] == "conversation"
        assert data["confidence"] == 0.9


class TestUserInfoStore:
    """Test UserInfoStore operations."""

    def test_get_info_empty_store(self):
        """Test getting info from empty store returns None."""
        store = UserInfoStore()
        assert store.get_info("email") is None

    def test_set_and_get_info(self):
        """Test setting and getting info."""
        store = UserInfoStore()
        store.set_info("email", "john@example.com")
        assert store.get_info("email") == "john@example.com"

    def test_set_info_with_metadata(self):
        """Test setting info with custom metadata."""
        store = UserInfoStore()
        store.set_info("phone", "555-1234", source="extracted", confidence=0.8)
        
        entry = store.user_info["phone"]
        assert entry.value == "555-1234"
        assert entry.source == "extracted"
        assert entry.confidence == 0.8

    def test_get_missing_fields(self):
        """Test identifying missing fields."""
        store = UserInfoStore()
        store.set_info("email", "john@example.com")
        store.set_info("name", "John Doe")
        
        required = ["email", "phone", "address"]
        missing = store.get_missing_fields(required)
        
        assert missing == ["phone", "address"]

    def test_update_from_dict(self):
        """Test bulk update from dictionary."""
        store = UserInfoStore()
        info_dict = {
            "email": "john@example.com",
            "phone": "555-1234",
            "name": "John Doe"
        }
        store.update_from_dict(info_dict, source="user_input")
        
        assert store.get_info("email") == "john@example.com"
        assert store.get_info("phone") == "555-1234"
        assert store.get_info("name") == "John Doe"
        
        # Check metadata
        assert store.user_info["email"].source == "user_input"

    def test_to_dict(self):
        """Test converting store to dict for JSON serialization."""
        store = UserInfoStore()
        store.set_info("email", "john@example.com")
        
        data = store.to_dict()
        assert "user_info" in data
        assert "email" in data["user_info"]
        assert data["user_info"]["email"]["value"] == "john@example.com"
        assert data["version"] == "1.0"

    def test_from_dict(self):
        """Test creating store from dict."""
        data = {
            "user_info": {
                "email": {
                    "value": "john@example.com",
                    "source": "user_input",
                    "confidence": 1.0,
                    "last_updated": "2026-07-27T12:00:00Z"
                }
            },
            "version": "1.0",
            "last_sync": "2026-07-27T12:00:00Z"
        }
        
        store = UserInfoStore.from_dict(data)
        assert store.get_info("email") == "john@example.com"
        assert store.version == "1.0"

    def test_overwrite_existing_info(self):
        """Test that setting info overwrites existing."""
        store = UserInfoStore()
        store.set_info("email", "old@example.com")
        store.set_info("email", "new@example.com", source="updated")
        
        assert store.get_info("email") == "new@example.com"
        assert store.user_info["email"].source == "updated"


class TestUserInfoStorePersistence:
    """Test file persistence of user info store."""

    def test_get_store_path(self):
        """Test store path is in config directory."""
        path = get_store_path()
        assert path.parent.name == "plan-execute-agent"
        assert path.name == "user_info.json"

    def test_save_and_load(self, tmp_path):
        """Test saving and loading store from file."""
        # Override store path for testing
        import src.tools.user_info_store as store_module
        original_get_path = store_module.get_store_path
        
        def mock_get_path():
            return tmp_path / "test_user_info.json"
        
        store_module.get_store_path = mock_get_path
        
        try:
            reset_user_info_store()
            
            # Use global store for save/load
            store = get_user_info_store()
            store.set_info("email", "john@example.com")
            store.set_info("name", "John Doe")
            save_user_info_store()
            
            # Load store
            loaded_store = load_user_info_store()
            assert loaded_store.get_info("email") == "john@example.com"
            assert loaded_store.get_info("name") == "John Doe"
            
        finally:
            store_module.get_store_path = original_get_path
            reset_user_info_store()

    def test_load_creates_new_if_missing(self, tmp_path):
        """Test loading creates new store if file doesn't exist."""
        import src.tools.user_info_store as store_module
        original_get_path = store_module.get_store_path
        
        def mock_get_path():
            return tmp_path / "nonexistent.json"
        
        store_module.get_store_path = mock_get_path
        
        try:
            store = load_user_info_store()
            assert isinstance(store, UserInfoStore)
            assert len(store.user_info) == 0
            
        finally:
            store_module.get_store_path = original_get_path
            reset_user_info_store()

    def test_global_store_singleton(self, tmp_path):
        """Test that global store is reused across calls."""
        import src.tools.user_info_store as store_module
        original_get_path = store_module.get_store_path
        
        def mock_get_path():
            return tmp_path / "test_singleton.json"
        
        store_module.get_store_path = mock_get_path
        
        try:
            reset_user_info_store()
            
            store1 = get_user_info_store()
            store1.set_info("email", "test@example.com")
            
            store2 = get_user_info_store()
            assert store2.get_info("email") == "test@example.com"
            assert store1 is store2
            
        finally:
            store_module.get_store_path = original_get_path
            reset_user_info_store()

    def test_reset_global_store(self):
        """Test resetting global store."""
        store1 = get_user_info_store()
        store1.set_info("email", "test@example.com")
        
        reset_user_info_store()
        
        store2 = get_user_info_store()
        assert store2.get_info("email") is None
        assert store1 is not store2


class TestUserInfoStoreIntegration:
    """Integration tests for user info store with form filling."""

    def test_auto_fill_empty_fields(self):
        """Test that empty fields are auto-filled from store."""
        store = UserInfoStore()
        store.set_info("email", "stored@example.com")
        store.set_info("name", "Stored Name")
        
        fields = {
            "email": "",  # Empty - should be filled
            "name": "",   # Empty - should be filled
            "phone": "555-0000"  # Not empty - should not be overwritten
        }
        
        # Simulate auto-fill logic
        for key in fields.keys():
            if not fields[key]:
                stored_value = store.get_info(key)
                if stored_value:
                    fields[key] = stored_value
        
        assert fields["email"] == "stored@example.com"
        assert fields["name"] == "Stored Name"
        assert fields["phone"] == "555-0000"  # Unchanged
