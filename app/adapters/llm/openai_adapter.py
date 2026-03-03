"""OpenAI LLM adapter."""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.domain.exceptions.domain_exceptions import LLMError
from app.domain.interfaces.llm_port import DeepAnalysisResult, LLMPort, QuickAnalysisResult

logger = logging.getLogger(__name__)

_QUICK_SYSTEM_PROMPT = """You are an expert Site Reliability Engineer analyzing JIRA incidents.
Given a new JIRA ticket and similar resolved tickets, provide a concise fix summary.
Respond in exactly 4 bullet points (3-5 lines total). Be specific, actionable, and direct.
Focus on: root cause, immediate fix, verification step, and prevention."""

_DEEP_SYSTEM_PROMPT = """You are a senior Platform Engineer conducting deep incident analysis.
You have access to similar resolved JIRA tickets. Provide comprehensive structured analysis.
Your response MUST be valid JSON matching the provided schema exactly."""

_DEEP_SCHEMA = {
    "root_cause": "string - specific technical root cause",
    "resolution_reasoning": "string - detailed explanation of why this resolution works",
    "risk_notes": "string - deployment risks and mitigations",
    "step_by_step_fix": ["array", "of", "strings"],
    "related_patterns": ["array", "of", "pattern", "names"],
    "confidence_explanation": "string - why confidence score was assigned",
}


def _format_similar_tickets(similar_tickets: list[dict[str, Any]], max_items: int = 5) -> str:
    lines = []
    for i, t in enumerate(similar_tickets[:max_items], 1):
        lines.append(
            f"[{i}] {t.get('jira_id', '?')} (sim: {t.get('similarity_score', 0):.2f})\n"
            f"    Summary: {t.get('summary', '')[:200]}\n"
            f"    Resolution: {t.get('resolution', '')[:300] or 'N/A'}"
        )
    return "\n\n".join(lines)


class OpenAILLMAdapter(LLMPort):
    """Production OpenAI LLM adapter."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens

    @property
    def model_version(self) -> str:
        return self._model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _chat_complete(self, messages: list[dict], max_tokens: int) -> ChatCompletion:
        return await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self._temperature,
            response_format={"type": "text"},
        )

    async def quick_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> QuickAnalysisResult:
        similar_context = _format_similar_tickets(similar_tickets)
        user_message = (
            f"NEW TICKET:\n{query_ticket_text[:2000]}\n\n"
            f"SIMILAR RESOLVED TICKETS:\n{similar_context}\n\n"
            "Provide a concise 4-bullet fix summary."
        )
        messages = [
            {"role": "system", "content": _QUICK_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        try:
            response = await self._chat_complete(messages, max_tokens)
            content = response.choices[0].message.content or ""
            best_match = similar_tickets[0] if similar_tickets else {}
            return QuickAnalysisResult(
                summary=content.strip(),
                fix_suggestion=(
                    f"Based on {best_match.get('jira_id', 'N/A')}: {content[:200]}"
                ),
                model_version=self._model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                raw_response={"model": self._model, "finish_reason": response.choices[0].finish_reason},
            )
        except Exception as e:
            raise LLMError(str(e)) from e

    async def deep_analyze(
        self,
        query_ticket_text: str,
        similar_tickets: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> DeepAnalysisResult:
        similar_context = _format_similar_tickets(similar_tickets, max_items=8)
        schema_str = json.dumps(_DEEP_SCHEMA, indent=2)
        user_message = (
            f"NEW TICKET:\n{query_ticket_text[:3000]}\n\n"
            f"SIMILAR RESOLVED TICKETS:\n{similar_context}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n{schema_str}"
        )
        messages = [
            {"role": "system", "content": _DEEP_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        try:
            response = await self._chat_complete(messages, max_tokens)
            content = response.choices[0].message.content or "{}"
            # Strip markdown code blocks if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed = json.loads(content)
            return DeepAnalysisResult(
                root_cause=parsed.get("root_cause", ""),
                resolution_reasoning=parsed.get("resolution_reasoning", ""),
                risk_notes=parsed.get("risk_notes", ""),
                step_by_step_fix=parsed.get("step_by_step_fix", []),
                related_patterns=parsed.get("related_patterns", []),
                confidence_explanation=parsed.get("confidence_explanation", ""),
                model_version=self._model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                raw_response=parsed,
            )
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse JSON response: {e}") from e
        except Exception as e:
            raise LLMError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return bool(response.choices)
        except Exception:
            return False