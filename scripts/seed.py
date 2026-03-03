#!/usr/bin/env python3
"""
Seed script — creates initial users, model registry entries,
and triggers JIRA ingestion for local development.

Usage:
    python scripts/seed.py
    # or via Docker:
    docker compose exec backend python scripts/seed.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.infrastructure.database.session import get_session_factory
from app.models.model_registry import ModelRegistryModel
from app.models.user import UserModel
from app.repositories.user_repository import UserRepository
from app.security.password import hash_password

SEED_USERS = [
    {
        "email": "admin@example.com",
        "password": "AdminPass123!",
        "role": "admin",
    },
    {
        "email": "reviewer@example.com",
        "password": "ReviewerPass123!",
        "role": "reviewer",
    },
    {
        "email": "user@example.com",
        "password": "UserPass123!",
        "role": "user",
    },
]

SEED_MODELS = [
    {
        "model_name": "mock-embedding-v1",
        "model_type": "embedding",
        "version": "mock-v1-dim384",
        "provider": "mock",
        "is_active": True,
        "notes": "Mock embedding for local dev",
    },
    {
        "model_name": "mock-llm-v1.0",
        "model_type": "llm",
        "version": "mock-llm-v1.0",
        "provider": "mock",
        "is_active": True,
        "notes": "Mock LLM for local dev",
    },
    {
        "model_name": "text-embedding-ada-002",
        "model_type": "embedding",
        "version": "openai-text-embedding-ada-002",
        "provider": "openai",
        "is_active": False,
        "notes": "OpenAI production embedding",
    },
    {
        "model_name": "gpt-4o",
        "model_type": "llm",
        "version": "gpt-4o-2024-11-20",
        "provider": "openai",
        "is_active": False,
        "notes": "OpenAI GPT-4o production LLM",
    },
]


async def seed_users(session) -> None:
    user_repo = UserRepository(session)
    print("Seeding users...")
    for user_data in SEED_USERS:
        existing = await user_repo.get_by_email(user_data["email"])
        if existing:
            print(f"  [skip] {user_data['email']} already exists")
            continue
        user = UserModel(
            email=user_data["email"],
            hashed_password=hash_password(user_data["password"]),
            role=user_data["role"],
            is_active=True,
        )
        session.add(user)
        print(f"  [created] {user_data['email']} (role={user_data['role']})")
    await session.flush()


async def seed_model_registry(session) -> None:
    from sqlalchemy import select
    print("Seeding model registry...")
    for model_data in SEED_MODELS:
        stmt = select(ModelRegistryModel).where(
            ModelRegistryModel.model_name == model_data["model_name"],
            ModelRegistryModel.version == model_data["version"],
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            print(f"  [skip] {model_data['model_name']} v{model_data['version']} exists")
            continue
        model = ModelRegistryModel(**model_data)
        session.add(model)
        print(f"  [created] {model_data['model_name']} ({model_data['model_type']})")
    await session.flush()


async def seed_jira_tickets(session) -> None:
    from app.adapters.llm.embedding_adapters import get_embedding_adapter, get_jira_adapter
    from app.application.services.embedding_service import EmbeddingService
    from app.application.services.ingestion_service import IngestionService
    from app.infrastructure.vector_store.faiss_store import FAISSVectorStore
    from app.repositories.embedding_repository import EmbeddingRepository
    from app.repositories.ticket_repository import TicketRepository

    settings = get_settings()
    print(f"Ingesting mock JIRA tickets (projects={settings.jira_project_keys_list})...")

    vector_store = FAISSVectorStore()
    await vector_store.load()

    ticket_repo = TicketRepository(session)
    embedding_repo = EmbeddingRepository(session)
    embedding_svc = EmbeddingService(
        embedding_adapter=get_embedding_adapter(),
        vector_store=vector_store,
        embedding_repo=embedding_repo,
        ticket_repo=ticket_repo,
    )
    ingestion_svc = IngestionService(
        jira_adapter=get_jira_adapter(),
        ticket_repo=ticket_repo,
        embedding_service=embedding_svc,
    )

    stats = await ingestion_svc.sync_all_projects(incremental=False)
    await session.flush()

    print(
        f"  Ingestion complete: {stats['new_tickets']} new tickets, "
        f"{stats['newly_indexed']} indexed"
    )

    vector_count = vector_store.count()
    print(f"  FAISS index now contains {vector_count} vectors")


async def main() -> None:
    print("=" * 60)
    print("JIRA Resolution Intelligence — Seed Script")
    print("=" * 60)

    factory = get_session_factory()
    async with factory() as session:
        await seed_users(session)
        await seed_model_registry(session)
        await seed_jira_tickets(session)
        await session.commit()

    print()
    print("=" * 60)
    print("Seed complete!")
    print()
    print("Default credentials:")
    for user in SEED_USERS:
        print(f"  {user['role']:10s}  {user['email']}  /  {user['password']}")
    print()
    print("API available at:  http://localhost:8000")
    print("API docs at:       http://localhost:8000/docs")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())