"""Anthropic Claude LLM adapter."""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.domain.exceptions.domain_exceptions import LLMError
from app.domain.interfaces.llm_port import DeepAnalysisResult, LLMPort, QuickAnalysisResult

logger = logging.getLogger(__name__)

_QUICK_SYSTEM = (
    "You are an expert SRE analyzing JIRA incidents. "
    "Given a new ticket and similar resolved tickets, provide exactly 4 actionable bullet points "
    "(3-5 lines total) covering: root cause, fix, verification, and prevention. Be specific."
)

_DEEP_SYSTEM = (
    "You are a senior Platform Engineer conducting deep incident analysis. "
    "Analyze the provided JIRA ticket and similar resolved incidents. "
    "Respond ONLY with a valid JSON object — no prose, no markdown, just JSON."
)


def _format_similar(tickets: list[dict[str, Any]], max_items: int = 5) -> str:
    parts = []
    for i, t in enumerate(tickets[:max_items], 1):
        parts.append(
            f"[{i}] {t.get('jira_id', '?')} (similarity={t.get('similarity_score', 0):.2f})\n"
            f"Summary: {t.get('summary', '')[:200]}\n"
            f"Resolution: {(t.get('resolution') or 'N/A')[:300]}"
        )
    return "\n\n".join(parts)


class AnthropicLLMAdapter(LLMPort):
    """Production Anthropic Claude LLM adapter."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model if "claude" in settings.llm_model else "claude-opus-4-6"
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    @property
    def model_version(self) -> str:
        return self._model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _message(
        self, system: str, user_content: str, max_tokens: int
    ) -> anthropic.types.Message:
        return await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )

    async def quick_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> QuickAnalysisResult:
        user_content = (
            f"NEW TICKET:\n{query_ticket_text[:2000]}\n\n"
            f"SIMILAR RESOLVED:\n{_format_similar(similar_tickets)}"
        )
        try:
            msg = await self._message(_QUICK_SYSTEM, user_content, max_tokens)
            text = msg.content[0].text if msg.content else ""
            best = similar_tickets[0] if similar_tickets else {}
            return QuickAnalysisResult(
                summary=text.strip(),
                fix_suggestion=f"Based on {best.get('jira_id', 'N/A')}: {text[:200]}",
                model_version=self._model,
                tokens_used=msg.usage.input_tokens + msg.usage.output_tokens,
                raw_response={"stop_reason": msg.stop_reason, "model": self._model},
            )
        except Exception as e:
            raise LLMError(str(e)) from e

    async def deep_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> DeepAnalysisResult:
        schema = {
            "root_cause": "<string>",
            "resolution_reasoning": "<string>",
            "risk_notes": "<string>",
            "step_by_step_fix": ["<string>"],
            "related_patterns": ["<string>"],
            "confidence_explanation": "<string>",
        }
        user_content = (
            f"NEW TICKET:\n{query_ticket_text[:3000]}\n\n"
            f"SIMILAR RESOLVED:\n{_format_similar(similar_tickets, max_items=8)}\n\n"
            f"Respond ONLY with valid JSON matching:\n{json.dumps(schema, indent=2)}"
        )
        try:
            msg = await self._message(_DEEP_SYSTEM, user_content, max_tokens)
            raw_text = msg.content[0].text if msg.content else "{}"
            raw_text = raw_text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            parsed = json.loads(raw_text)
            return DeepAnalysisResult(
                root_cause=parsed.get("root_cause", ""),
                resolution_reasoning=parsed.get("resolution_reasoning", ""),
                risk_notes=parsed.get("risk_notes", ""),
                step_by_step_fix=parsed.get("step_by_step_fix", []),
                related_patterns=parsed.get("related_patterns", []),
                confidence_explanation=parsed.get("confidence_explanation", ""),
                model_version=self._model,
                tokens_used=msg.usage.input_tokens + msg.usage.output_tokens,
                raw_response=parsed,
            )
        except json.JSONDecodeError as e:
            raise LLMError(f"JSON parse error: {e}") from e
        except Exception as e:
            raise LLMError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            msg = await self._client.messages.create(
                model=self._model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return bool(msg.content)
        except Exception:
            return False