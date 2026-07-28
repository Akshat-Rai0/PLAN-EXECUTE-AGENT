"""
User information persistence store for form filling automation.

Stores user personal information (name, email, phone, etc.) with metadata
to enable intelligent form filling and reduce redundant data entry.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field


class UserInfoEntry(BaseModel):
    """Single user information entry with metadata."""
    value: str
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "user_input"  # user_input, conversation, extracted
    confidence: float = 1.0  # 0.0 to 1.0


class UserInfoStore(BaseModel):
    """Global user information store with metadata."""
    user_info: dict[str, UserInfoEntry] = Field(default_factory=dict)
    version: str = "1.0"
    last_sync: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_info(self, key: str) -> Optional[str]:
        """Retrieve user information by key."""
        entry = self.user_info.get(key)
        return entry.value if entry else None

    def set_info(self, key: str, value: str, source: str = "user_input", confidence: float = 1.0) -> None:
        """Store user information with metadata."""
        self.user_info[key] = UserInfoEntry(
            value=value,
            source=source,
            confidence=confidence
        )
        self.last_sync = datetime.now(timezone.utc).isoformat()

    def get_missing_fields(self, required_fields: list[str]) -> list[str]:
        """Identify which required fields are missing from the store."""
        return [field for field in required_fields if field not in self.user_info]

    def update_from_dict(self, info_dict: dict[str, str], source: str = "user_input") -> None:
        """Bulk update user info from a dictionary."""
        for key, value in info_dict.items():
            self.set_info(key, value, source)

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for JSON serialization."""
        return {
            "user_info": {
                key: entry.model_dump()
                for key, entry in self.user_info.items()
            },
            "version": self.version,
            "last_sync": self.last_sync
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserInfoStore":
        """Create from plain dict (from JSON)."""
        user_info = {}
        for key, entry_data in data.get("user_info", {}).items():
            user_info[key] = UserInfoEntry(**entry_data)
        return cls(
            user_info=user_info,
            version=data.get("version", "1.0"),
            last_sync=data.get("last_sync", datetime.now(timezone.utc).isoformat())
        )


# Global store instance
_global_store: Optional[UserInfoStore] = None


def get_store_path() -> Path:
    """Get the path to the user info JSON file."""
    config_dir = Path.home() / ".config" / "plan-execute-agent"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "user_info.json"


def load_user_info_store() -> UserInfoStore:
    """Load user info store from disk, creating new if doesn't exist."""
    global _global_store
    
    if _global_store is not None:
        return _global_store
    
    store_path = get_store_path()
    
    if store_path.exists():
        try:
            with open(store_path, "r") as f:
                data = json.load(f)
            _global_store = UserInfoStore.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Corrupted file, start fresh
            _global_store = UserInfoStore()
    else:
        _global_store = UserInfoStore()
    
    return _global_store


def save_user_info_store() -> None:
    """Save user info store to disk."""
    global _global_store
    
    if _global_store is None:
        return
    
    store_path = get_store_path()
    with open(store_path, "w") as f:
        json.dump(_global_store.to_dict(), f, indent=2)


def get_user_info_store() -> UserInfoStore:
    """Get the global user info store instance."""
    return load_user_info_store()


def reset_user_info_store() -> None:
    """Reset the global store (for testing)."""
    global _global_store
    _global_store = None
