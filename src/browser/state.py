import os
from src.models.browser_models import BrowserState, BrowserAction

class StateManager:
    def __init__(self):
        self.state = BrowserState()
        self._load_profile()

    def _load_profile(self):
        """Loads profile from environment variables."""
        profile_keys = ["NAME", "EMAIL", "PHONE", "DOB", "COLLEGE", "GITHUB", "LINKEDIN", "RESUME", "SKILLS"]
        for key in profile_keys:
            val = os.environ.get(f"PROFILE_{key}")
            if val:
                self.state.profile[key.lower()] = val

    def record_action(self, action: BrowserAction):
        self.state.completed_actions.append(action)

    def record_visit(self, url: str):
        if url not in self.state.visited_pages:
            self.state.visited_pages.append(url)

    def record_field_fill(self, field_id: int, value: str):
        self.state.filled_fields[field_id] = value

    def set_task(self, task: str):
        self.state.current_task = task

    def get_profile_value(self, key: str) -> str:
        return self.state.profile.get(key.lower(), "")
