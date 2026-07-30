"""
Structured output models for browser pipelines.

Provides Pydantic models for typed, validated results from each pipeline.
"""
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


# Form Filling Models
class FormField(BaseModel):
    """A single form field on a page."""
    name: str = Field(..., description="Logical name or label of the field")
    type: str = Field(..., description="Field type: text, dropdown, checkbox, radio, etc.")
    selector: str = Field(..., description="CSS selector to target the field")
    required: bool = Field(default=False, description="Whether the field is required")
    current_value: Optional[str] = Field(default=None, description="Current text or selection")


class FormFillResult(BaseModel):
    """Result of form filling operation."""
    fields_filled: list[str] = Field(default_factory=list, description="Names of fields that were filled")
    success: bool = Field(default=False, description="Whether form submission succeeded")
    validation_message: Optional[str] = Field(default=None, description="Validation message from the page")
    error: Optional[str] = Field(default=None, description="Error message if filling failed")


# Booking Models
class BookingOption(BaseModel):
    """A single booking option."""
    price: float = Field(..., description="Price of the option")
    duration: Optional[str] = Field(default=None, description="Duration of the booking")
    timing: Optional[str] = Field(default=None, description="Timing/schedule of the booking")
    provider: str = Field(..., description="Provider or company name")
    url: Optional[str] = Field(default=None, description="URL to book this option")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Additional attributes")


class BookingRecommendation(BaseModel):
    """Booking recommendation with alternatives."""
    selected_option: Optional[BookingOption] = Field(default=None, description="The recommended option")
    alternatives: list[BookingOption] = Field(default_factory=list, description="Alternative options")
    reasoning: str = Field(..., description="Reasoning for the recommendation")
    criteria: str = Field(..., description="Criteria used for selection")


# Comparison Models
class ComparisonItem(BaseModel):
    """A single item for comparison."""
    title: str = Field(..., description="Product or item title")
    price: float = Field(..., description="Price of the item")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Key attributes for comparison")
    source: str = Field(..., description="Source website or platform")
    url: str = Field(..., description="Full URL to the item")
    condition: Optional[str] = Field(default=None, description="Condition: New, Used, Refurbished, etc")


class ComparisonResult(BaseModel):
    """Result of comparison operation."""
    items: list[ComparisonItem] = Field(default_factory=list, description="All items compared")
    best_match: Optional[ComparisonItem] = Field(default=None, description="Best matching item")
    criteria: str = Field(..., description="Criteria used for comparison")
    search_query: str = Field(..., description="Original search query")


# Data Collection Models
class DataPoint(BaseModel):
    """A single data point collected from a source."""
    url: str = Field(..., description="Source URL")
    data: dict[str, Any] = Field(default_factory=dict, description="Extracted data")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Collection timestamp")
    confidence: float = Field(default=1.0, description="Confidence score (0-1)")


class CollectionResult(BaseModel):
    """Result of data collection operation."""
    points: list[DataPoint] = Field(default_factory=list, description="All data points collected")
    failed_urls: list[str] = Field(default_factory=list, description="URLs that failed to extract")
    aggregated_data: dict[str, Any] = Field(default_factory=dict, description="Aggregated/merged data")
    extraction_goal: str = Field(..., description="Original extraction goal")


# Info Retrieval Models
class InfoResult(BaseModel):
    """Result of information retrieval operation."""
    answer: str = Field(..., description="The answer or information retrieved")
    source_url: str = Field(..., description="URL where the answer was found")
    confidence: float = Field(default=1.0, description="Confidence in the answer (0-1)")
    related_links: list[str] = Field(default_factory=list, description="Related URLs for context")
    query: str = Field(..., description="Original query")
