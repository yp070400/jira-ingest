"""Initial schema — all core tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_email_active", "users", ["email", "is_active"])

    # ── jira_tickets ───────────────────────────────────────────────────────
    op.create_table(
        "jira_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("jira_id", sa.String(64), nullable=False),
        sa.Column("project_key", sa.String(32), nullable=False),
        sa.Column("summary", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(32), nullable=False, server_default="Unknown"),
        sa.Column("reporter", sa.String(255), nullable=True),
        sa.Column("assignee", sa.String(255), nullable=True),
        sa.Column("labels", JSONB(), nullable=True),
        sa.Column("components", JSONB(), nullable=True),
        sa.Column("fix_versions", JSONB(), nullable=True),
        sa.Column("raw_data", JSONB(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("embedding_version", sa.String(64), nullable=True),
        sa.Column("jira_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_jira_tickets_jira_id", "jira_tickets", ["jira_id"], unique=True)
    op.create_index("ix_jira_tickets_project_key", "jira_tickets", ["project_key"])
    op.create_index("ix_jira_tickets_status", "jira_tickets", ["status"])
    op.create_index("ix_jira_tickets_project_status", "jira_tickets", ["project_key", "status"])
    op.create_index("ix_jira_tickets_embedding_version", "jira_tickets", ["embedding_version"])
    op.create_index("ix_jira_tickets_is_indexed", "jira_tickets", ["is_indexed"])
    op.create_index("ix_jira_tickets_quality_score", "jira_tickets", ["quality_score"])
    op.create_index("ix_jira_tickets_resolved_at", "jira_tickets", ["resolved_at"])

    # ── embeddings ─────────────────────────────────────────────────────────
    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("jira_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vector_version", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_hash", sa.String(64), nullable=False),
        sa.Column("faiss_index_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_embeddings_ticket_id", "embeddings", ["ticket_id"], unique=True)
    op.create_index("ix_embeddings_vector_version", "embeddings", ["vector_version"])
    op.create_index("ix_embeddings_embedding_hash", "embeddings", ["embedding_hash"])
    op.create_index("ix_embeddings_faiss_index_id", "embeddings", ["faiss_index_id"])
    op.create_index("ix_embeddings_version_model", "embeddings", ["vector_version", "model_name"])

    # ── feedback ───────────────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_ticket_id", sa.String(64), nullable=False),
        sa.Column(
            "suggested_ticket_id",
            sa.String(36),
            sa.ForeignKey("jira_tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("embedding_version", sa.String(64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("was_helpful", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("was_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "reviewer_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_feedback_query_ticket_id", "feedback", ["query_ticket_id"])
    op.create_index("ix_feedback_suggested_ticket_id", "feedback", ["suggested_ticket_id"])
    op.create_index("ix_feedback_reviewer_id", "feedback", ["reviewer_id"])
    op.create_index("ix_feedback_rating", "feedback", ["rating"])

    # ── reranking_weights ──────────────────────────────────────────────────
    op.create_table(
        "reranking_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feature_name", sa.String(128), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("feedback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_rating", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("last_recalibrated_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_reranking_weights_feature_name", "reranking_weights", ["feature_name"], unique=True
    )

    # ── model_registry ─────────────────────────────────────────────────────
    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_type", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("config", JSONB(), nullable=True),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_model_registry_model_name", "model_registry", ["model_name"])
    op.create_index(
        "ix_model_registry_type_active", "model_registry", ["model_type", "is_active"]
    )

    # ── audit_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_action_status", "audit_logs", ["action", "status"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("model_registry")
    op.drop_table("reranking_weights")
    op.drop_table("feedback")
    op.drop_table("embeddings")
    op.drop_table("jira_tickets")
    op.drop_table("users")