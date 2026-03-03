"""Domain-layer exceptions — framework agnostic."""
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class TicketNotFoundError(DomainError):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Ticket '{ticket_id}' not found", "TICKET_NOT_FOUND")
        self.ticket_id = ticket_id


class TicketAlreadyExistsError(DomainError):
    def __init__(self, jira_id: str) -> None:
        super().__init__(f"Ticket '{jira_id}' already exists", "TICKET_ALREADY_EXISTS")
        self.jira_id = jira_id


class EmbeddingNotFoundError(DomainError):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(
            f"No embedding found for ticket '{ticket_id}'", "EMBEDDING_NOT_FOUND"
        )


class UserNotFoundError(DomainError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"User '{identifier}' not found", "USER_NOT_FOUND")


class UserAlreadyExistsError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"User with email '{email}' already exists", "USER_ALREADY_EXISTS")


class InvalidCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__("Invalid credentials", "INVALID_CREDENTIALS")


class InsufficientPermissionsError(DomainError):
    def __init__(self, required_role: str) -> None:
        super().__init__(
            f"Insufficient permissions. Required role: {required_role}",
            "INSUFFICIENT_PERMISSIONS",
        )


class InvalidAnalysisModeError(DomainError):
    def __init__(self, mode: str) -> None:
        super().__init__(f"Invalid analysis mode: '{mode}'", "INVALID_ANALYSIS_MODE")


class VectorIndexError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Vector index error: {reason}", "VECTOR_INDEX_ERROR")


class EmbeddingGenerationError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Embedding generation failed: {reason}", "EMBEDDING_GENERATION_ERROR")


class LLMError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"LLM request failed: {reason}", "LLM_ERROR")


class JiraIngestionError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"JIRA ingestion error: {reason}", "JIRA_INGESTION_ERROR")


class FeedbackNotFoundError(DomainError):
    def __init__(self, feedback_id: str) -> None:
        super().__init__(f"Feedback '{feedback_id}' not found", "FEEDBACK_NOT_FOUND")


class RateLimitExceededError(DomainError):
    def __init__(self, limit: int, window: int) -> None:
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window} seconds",
            "RATE_LIMIT_EXCEEDED",
        )
        self.limit = limit
        self.window = window


class ConfigurationError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Configuration error: {reason}", "CONFIGURATION_ERROR")