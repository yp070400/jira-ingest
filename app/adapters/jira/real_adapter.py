"""Real JIRA REST API adapter using Atlassian REST API v3."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.domain.entities.ticket import TicketEntity, TicketStatus
from app.domain.exceptions.domain_exceptions import JiraIngestionError
from app.domain.interfaces.jira_port import JiraPort

logger = logging.getLogger(__name__)

_JIRA_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _parse_jira_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_labels(fields: dict[str, Any]) -> list[str]:
    return fields.get("labels", []) or []


def _extract_components(fields: dict[str, Any]) -> list[str]:
    components = fields.get("components", []) or []
    return [c.get("name", "") for c in components if c.get("name")]


def _extract_fix_versions(fields: dict[str, Any]) -> list[str]:
    versions = fields.get("fixVersions", []) or []
    return [v.get("name", "") for v in versions if v.get("name")]


def _extract_user_email(user_obj: dict[str, Any] | None) -> str | None:
    if not user_obj:
        return None
    return user_obj.get("emailAddress") or user_obj.get("displayName")


class RealJiraAdapter(JiraPort):
    """
    Production JIRA REST API adapter.
    Uses Atlassian REST API v3 with basic auth (API token).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.jira_base_url.rstrip("/")
        self._api_base = f"{self._base_url}/rest/api/{settings.jira_api_version}"
        self._auth = (settings.jira_username, settings.jira_api_token)
        self._max_results = settings.jira_max_results_per_page
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=self._auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    def _build_jql(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
    ) -> str:
        projects_str = ", ".join(f'"{p}"' for p in project_keys)
        statuses_str = ", ".join(f'"{s}"' for s in resolved_statuses)
        jql = f"project in ({projects_str}) AND status in ({statuses_str})"
        if since:
            since_str = since.strftime("%Y-%m-%d %H:%M")
            jql += f' AND updated >= "{since_str}"'
        jql += " ORDER BY updated DESC"
        return jql

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _search_issues(
        self, jql: str, start_at: int = 0, max_results: int = 100
    ) -> dict[str, Any]:
        url = f"{self._api_base}/search"
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": (
                "summary,description,status,resolution,priority,"
                "reporter,assignee,labels,components,fixVersions,"
                "created,updated,resolutiondate,comment"
            ),
        }
        client = self._get_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise JiraIngestionError(
                f"JIRA API returned {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.RequestError as e:
            raise JiraIngestionError(f"Network error connecting to JIRA: {e}") from e

    def _map_to_entity(self, issue: dict[str, Any]) -> TicketEntity:
        fields = issue.get("fields", {})
        jira_id = issue.get("key", "")
        project_key = jira_id.split("-")[0] if "-" in jira_id else ""

        resolution_obj = fields.get("resolution")
        resolution_text = resolution_obj.get("description") if resolution_obj else None
        if not resolution_text:
            resolution_text = resolution_obj.get("name") if resolution_obj else None

        status_obj = fields.get("status", {})
        status = status_obj.get("name", "Unknown")

        priority_obj = fields.get("priority", {})
        priority = priority_obj.get("name", "Unknown")

        # Extract description from Atlassian Document Format (ADF) or plain text
        description_field = fields.get("description")
        description = self._extract_text_from_adf(description_field)

        ticket = TicketEntity(
            jira_id=jira_id,
            project_key=project_key,
            summary=fields.get("summary", ""),
            description=description,
            status=status,
            resolution=resolution_text,
            priority=priority,
            reporter=_extract_user_email(fields.get("reporter")),
            assignee=_extract_user_email(fields.get("assignee")),
            labels=_extract_labels(fields),
            components=_extract_components(fields),
            fix_versions=_extract_fix_versions(fields),
            created_at=_parse_jira_date(fields.get("created")),
            updated_at=_parse_jira_date(fields.get("updated")),
            resolved_at=_parse_jira_date(fields.get("resolutiondate")),
            raw_data={
                "comments": fields.get("comment", {}).get("comments", []),
                "issue_links": fields.get("issuelinks", []),
            },
        )
        ticket.compute_quality_score()
        return ticket

    def _extract_text_from_adf(self, content: Any) -> str | None:
        """Extract plain text from Atlassian Document Format."""
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if not isinstance(content, dict):
            return None

        parts: list[str] = []

        def traverse(node: dict) -> None:
            node_type = node.get("type", "")
            if node_type == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []):
                traverse(child)
            if node_type in ("paragraph", "heading", "listItem"):
                parts.append("\n")

        traverse(content)
        return "".join(parts).strip() or None

    async def fetch_resolved_tickets(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
        max_results: int = 100,
    ) -> list[TicketEntity]:
        jql = self._build_jql(project_keys, resolved_statuses, since)
        tickets: list[TicketEntity] = []
        start_at = 0

        while True:
            data = await self._search_issues(jql, start_at=start_at, max_results=self._max_results)
            issues = data.get("issues", [])

            for issue in issues:
                try:
                    tickets.append(self._map_to_entity(issue))
                except Exception as e:
                    logger.warning("Failed to map JIRA issue %s: %s", issue.get("key"), e)

            total = data.get("total", 0)
            start_at += len(issues)

            if start_at >= total or start_at >= max_results or not issues:
                break

        logger.info("Fetched %d tickets from JIRA (projects=%s)", len(tickets), project_keys)
        return tickets[:max_results]

    async def fetch_ticket_by_id(self, jira_id: str) -> TicketEntity | None:
        url = f"{self._api_base}/issue/{quote(jira_id)}"
        params = {
            "fields": (
                "summary,description,status,resolution,priority,"
                "reporter,assignee,labels,components,fixVersions,"
                "created,updated,resolutiondate,comment"
            )
        }
        client = self._get_client()
        try:
            response = await client.get(url, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return self._map_to_entity(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise JiraIngestionError(f"JIRA API error for {jira_id}: {e}") from e

    async def health_check(self) -> bool:
        url = f"{self._api_base}/myself"
        client = self._get_client()
        try:
            response = await client.get(url, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def get_total_count(
        self,
        project_keys: list[str],
        resolved_statuses: list[str],
        since: datetime | None = None,
    ) -> int:
        jql = self._build_jql(project_keys, resolved_statuses, since)
        data = await self._search_issues(jql, start_at=0, max_results=1)
        return data.get("total", 0)

    @property
    def api_base(self) -> str:
        return self._api_base