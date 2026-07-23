from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class ExtractedElement(BaseModel):
    id: int
    tag: str
    text: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    
class ExtractedForm(BaseModel):
    id: int
    action: Optional[str] = None
    inputs: List[ExtractedElement] = Field(default_factory=list)
    buttons: List[ExtractedElement] = Field(default_factory=list)

class PageSummary(BaseModel):
    url: str
    title: str
    headings: List[ExtractedElement] = Field(default_factory=list)
    links: List[ExtractedElement] = Field(default_factory=list)
    forms: List[ExtractedForm] = Field(default_factory=list)
    buttons: List[ExtractedElement] = Field(default_factory=list)
    inputs: List[ExtractedElement] = Field(default_factory=list)
    paragraphs: List[str] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)

class BrowserAction(BaseModel):
    action: str = Field(description="Action to perform (e.g., 'goto', 'click', 'type', 'select', 'upload', 'scroll', 'wait', 'extract', 'finish')")
    target: Optional[int] = Field(None, description="The integer ID of the target element")
    value: Optional[str] = Field(None, description="The value to type or select, or URL to goto")
    
class BrowserState(BaseModel):
    visited_pages: List[str] = Field(default_factory=list)
    completed_actions: List[BrowserAction] = Field(default_factory=list)
    current_task: Optional[str] = None
    filled_fields: Dict[int, str] = Field(default_factory=dict)
    downloaded_files: List[str] = Field(default_factory=list)
    profile: Dict[str, str] = Field(default_factory=dict)
