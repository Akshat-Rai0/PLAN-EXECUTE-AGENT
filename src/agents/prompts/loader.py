"""Load a versioned prompt template without coupling agent modules to paths."""

from pathlib import Path


def load_prompt(arm: str, name: str) -> str:
    """Return the exact template stored for an agent arm and prompt name."""
    path = Path(__file__).parent / arm / f"{name}.md"
    return path.read_text(encoding="utf-8").removesuffix("\n")
