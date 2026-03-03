"""APScheduler-based background job scheduler."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            }
        )
    return _scheduler


def start_scheduler(
    ingestion_fn,
    feedback_aggregation_fn,
    embedding_health_fn,
) -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = get_scheduler()

    # ── JIRA Incremental Sync ─────────────────────────────────────────────
    scheduler.add_job(
        ingestion_fn,
        trigger=CronTrigger.from_crontab(settings.ingestion_cron),
        id="jira_incremental_sync",
        name="JIRA Incremental Sync",
        replace_existing=True,
    )
    logger.info("Scheduled JIRA sync: %s", settings.ingestion_cron)

    # ── Feedback Aggregation ──────────────────────────────────────────────
    scheduler.add_job(
        feedback_aggregation_fn,
        trigger=CronTrigger.from_crontab(settings.feedback_aggregation_cron),
        id="feedback_aggregation",
        name="Feedback Aggregation & Reranking",
        replace_existing=True,
    )
    logger.info("Scheduled feedback aggregation: %s", settings.feedback_aggregation_cron)

    # ── Embedding Health Check ────────────────────────────────────────────
    scheduler.add_job(
        embedding_health_fn,
        trigger=CronTrigger.from_crontab(settings.embedding_health_cron),
        id="embedding_health_check",
        name="Embedding Health Check",
        replace_existing=True,
    )
    logger.info("Scheduled embedding health check: %s", settings.embedding_health_cron)

    scheduler.start()
    logger.info("Background scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler stopped")
