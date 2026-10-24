from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    title: str
    url: str


class SchemeAdviceOut(BaseModel):
    scheme_code: str
    display_name: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    rationale: str
    risks: list[str] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    model: str
    disclaimer: str
    generated_at: datetime | None = None


class PortfolioActionOut(BaseModel):
    scheme_code: str | None = None
    scheme_name: str
    action: Literal["INCREASE", "REDUCE", "EXIT", "REPLACE", "HOLD"]
    suggestion: str
    rationale: str


class PortfolioAdviceOut(BaseModel):
    summary: str
    actions: list[PortfolioActionOut] = Field(default_factory=list)
    diversification_notes: list[str] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    model: str
    disclaimer: str
    generated_at: datetime | None = None