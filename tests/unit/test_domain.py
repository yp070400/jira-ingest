"""Unit tests for domain entities and value objects."""
from __future__ import annotations

import pytest

from app.domain.entities.ticket import TicketEntity, TicketStatus
from app.domain.entities.user import ROLE_PERMISSIONS, UserEntity, UserRole
from app.domain.entities.feedback import FeedbackEntity
from app.domain.value_objects.score import ConfidenceScore, QualityScore, SimilarityScore
from app.domain.exceptions.domain_exceptions import (
    DomainError,
    TicketNotFoundError,
    InsufficientPermissionsError,
)


class TestSimilarityScore:
    def test_valid_score(self):
        s = SimilarityScore(0.85)
        assert s.value == 0.85

    def test_zero_score(self):
        s = SimilarityScore.zero()
        assert s.value == 0.0

    def test_perfect_score(self):
        s = SimilarityScore.perfect()
        assert s.value == 1.0

    def test_invalid_score_raises(self):
        with pytest.raises(ValueError):
            SimilarityScore(1.5)

    def test_is_above_threshold(self):
        s = SimilarityScore(0.8)
        assert s.is_above_threshold(0.7) is True
        assert s.is_above_threshold(0.9) is False

    def test_immutable(self):
        s = SimilarityScore(0.5)
        with pytest.raises(Exception):
            s.value = 0.9  # type: ignore


class TestConfidenceScore:
    def test_label_high(self):
        c = ConfidenceScore(0.9)
        assert c.label() == "HIGH"

    def test_label_medium(self):
        c = ConfidenceScore(0.7)
        assert c.label() == "MEDIUM"

    def test_label_low(self):
        c = ConfidenceScore(0.5)
        assert c.label() == "LOW"

    def test_label_very_low(self):
        c = ConfidenceScore(0.3)
        assert c.label() == "VERY_LOW"

    def test_requires_review_when_below_threshold(self):
        c = ConfidenceScore(0.55)
        assert c.requires_review(0.60) is True

    def test_no_review_when_above_threshold(self):
        c = ConfidenceScore(0.85)
        assert c.requires_review(0.60) is False


class TestQualityScore:
    def test_full_quality(self):
        score = QualityScore.from_ticket_metadata(
            has_description=True,
            has_resolution=True,
            has_labels=True,
            has_components=True,
            comment_count=5,
        )
        assert score.value > 0.9

    def test_minimal_quality(self):
        score = QualityScore.from_ticket_metadata(
            has_description=False,
            has_resolution=False,
            has_labels=False,
            has_components=False,
            comment_count=0,
        )
        assert score.value == 0.0


class TestTicketEntity:
    def test_is_resolved_done(self):
        t = TicketEntity(jira_id="T-1", project_key="T", summary="Test", status="Done")
        assert t.is_resolved is True

    def test_is_resolved_open(self):
        t = TicketEntity(jira_id="T-1", project_key="T", summary="Test", status="Open")
        assert t.is_resolved is False

    def test_searchable_text_includes_resolution(self):
        t = TicketEntity(
            jira_id="T-1",
            project_key="T",
            summary="DB connection issue",
            description="Connection pool exhausted",
            resolution="Increased pool size",
            status="Done",
        )
        text = t.searchable_text
        assert "DB connection issue" in text
        assert "Connection pool exhausted" in text
        assert "Increased pool size" in text

    def test_truncate_for_embedding(self):
        t = TicketEntity(
            jira_id="T-1",
            project_key="T",
            summary="X" * 100,
            description="Y" * 10000,
            status="Done",
        )
        truncated = t.truncate_for_embedding(max_chars=500)
        assert len(truncated) <= 503  # Allow for "..."


class TestUserEntity:
    def test_admin_has_all_permissions(self):
        user = UserEntity(
            email="admin@test.com",
            role=UserRole.ADMIN,
            hashed_password="hashed",
        )
        assert user.has_permission("analyze:deep")
        assert user.has_permission("admin:reindex")
        assert user.is_admin()

    def test_user_cannot_deep_analyze(self):
        user = UserEntity(
            email="user@test.com",
            role=UserRole.USER,
            hashed_password="hashed",
        )
        assert not user.can_access_deep_analysis()

    def test_reviewer_can_deep_analyze(self):
        user = UserEntity(
            email="reviewer@test.com",
            role=UserRole.REVIEWER,
            hashed_password="hashed",
        )
        assert user.can_access_deep_analysis()
        assert not user.is_admin()


class TestFeedbackEntity:
    def test_valid_feedback(self):
        from datetime import datetime, timezone
        fb = FeedbackEntity(
            query_ticket_id="PROJ-100",
            suggested_ticket_id="uuid-123",
            similarity_score=0.85,
            confidence_score=0.75,
            model_version="mock-v1",
            embedding_version="mock-embed-v1",
            rating=4,
            was_helpful=True,
            was_correct=True,
            reviewer_id="user-uuid",
        )
        assert fb.is_positive is True
        assert fb.normalized_rating == pytest.approx(0.75)

    def test_invalid_rating_raises(self):
        with pytest.raises(ValueError):
            FeedbackEntity(
                query_ticket_id="PROJ-100",
                suggested_ticket_id="uuid-123",
                similarity_score=0.8,
                confidence_score=0.7,
                model_version="v1",
                embedding_version="v1",
                rating=6,  # invalid
                was_helpful=True,
                was_correct=True,
                reviewer_id="user-1",
            )

    def test_decayed_signal_decreases_over_time(self):
        from datetime import datetime, timezone
        fb = FeedbackEntity(
            query_ticket_id="PROJ-100",
            suggested_ticket_id="uuid-123",
            similarity_score=0.85,
            confidence_score=0.75,
            model_version="v1",
            embedding_version="v1",
            rating=5,
            was_helpful=True,
            was_correct=True,
            reviewer_id="user-1",
        )
        signal_recent = fb.to_reranking_signal(decay_lambda=0.1, days_elapsed=1)
        signal_old = fb.to_reranking_signal(decay_lambda=0.1, days_elapsed=100)
        assert signal_recent > signal_old


class TestDomainExceptions:
    def test_ticket_not_found(self):
        exc = TicketNotFoundError("PROJ-999")
        assert exc.code == "TICKET_NOT_FOUND"
        assert "PROJ-999" in str(exc)

    def test_insufficient_permissions(self):
        exc = InsufficientPermissionsError("analyze:deep")
        assert exc.code == "INSUFFICIENT_PERMISSIONS"