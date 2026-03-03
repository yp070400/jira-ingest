"""Abstract LLM port."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class QuickAnalysisResult:
    summary: str
    fix_suggestion: str
    model_version: str
    tokens_used: int
    raw_response: dict[str, Any]


@dataclass
class DeepAnalysisResult:
    root_cause: str
    resolution_reasoning: str
    risk_notes: str
    step_by_step_fix: list[str]
    related_patterns: list[str]
    confidence_explanation: str
    model_version: str
    tokens_used: int
    raw_response: dict[str, Any]


class LLMPort(ABC):
    """Port (interface) for LLM provider adapters."""

    @abstractmethod
    async def quick_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> QuickAnalysisResult:
        """Generate a concise 3-5 line fix summary."""

    @abstractmethod
    async def deep_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> DeepAnalysisResult:
        """Generate comprehensive root-cause and resolution analysis."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the LLM provider."""

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Return the model identifier string."""