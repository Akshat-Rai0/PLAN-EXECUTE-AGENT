from typing import Dict, Optional

class SelectorManager:
    def __init__(self):
        self._id_to_selector: Dict[int, str] = {}
        self._current_id = 1

    def register(self, selector: str) -> int:
        """Register a new CSS/XPath selector and return a stable integer ID."""
        element_id = self._current_id
        self._id_to_selector[element_id] = selector
        self._current_id += 1
        return element_id

    def get_selector(self, element_id: int) -> Optional[str]:
        """Retrieve the actual selector for a given integer ID."""
        return self._id_to_selector.get(element_id)

    def clear(self):
        """Clear mappings, usually done on page navigation."""
        self._id_to_selector.clear()
        self._current_id = 1
