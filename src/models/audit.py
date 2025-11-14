"""
Audit data models for match processing tracking.

These models define the structure of audit log entries written to JSONL files.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Audit event types."""

    MATCH_DISCOVERED = "match_discovered"
    MATCH_UPDATED = "match_updated"
    MATCH_UNCHANGED = "match_unchanged"
    QUEUE_SUBMITTED = "queue_submitted"
    QUEUE_FAILED = "queue_failed"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"


class RunMetadata(BaseModel):
    """Metadata about a scraping run."""

    league: str | None = Field(None, description="League being scraped")
    age_group: str | None = Field(None, description="Age group filter")
    division: str | None = Field(None, description="Division or conference filter")
    date_range: str | None = Field(None, description="Date range being scraped")
    total_matches: int | None = Field(None, description="Total matches in this run")


class AuditEvent(BaseModel):
    """Base audit event model."""

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp (UTC)"
    )
    run_id: str = Field(..., description="Unique identifier for the scraping run")
    event_type: EventType = Field(..., description="Type of audit event")
    correlation_id: str | None = Field(
        None, description="Match ID for correlating related events"
    )
    run_metadata: RunMetadata | None = Field(
        None, description="Metadata about the scraping run"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "examples": [
                {
                    "timestamp": "2025-11-13T14:30:45.123Z",
                    "run_id": "20251113-143045-abc123",
                    "event_type": "run_started",
                    "correlation_id": None,
                    "run_metadata": {
                        "league": "Homegrown",
                        "age_group": "U14",
                        "division": "Northeast",
                        "date_range": "2025-10-01 to 2025-10-31",
                    },
                }
            ]
        }


class MatchAuditEvent(AuditEvent):
    """Audit event for match discovery or update."""

    match_data: dict[str, Any] | None = Field(
        None, description="Complete match data payload"
    )
    changes: dict[str, dict[str, Any]] | None = Field(
        None,
        description="Field-level changes (only for match_updated events)",
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "examples": [
                {
                    "timestamp": "2025-11-13T14:31:15.456Z",
                    "run_id": "20251113-143045-abc123",
                    "event_type": "match_updated",
                    "correlation_id": "100436",
                    "match_data": {
                        "home_team": "IFA",
                        "away_team": "NEFC",
                        "match_date": "2025-10-18",
                        "home_score": 5,
                        "away_score": 1,
                        "match_status": "completed",
                        "external_match_id": "100436",
                        "age_group": "U14",
                        "division": "Northeast",
                        "league": "Homegrown",
                    },
                    "changes": {
                        "match_status": {"from": "scheduled", "to": "completed"},
                        "home_score": {"from": None, "to": 5},
                        "away_score": {"from": None, "to": 1},
                    },
                    "run_metadata": {
                        "league": "Homegrown",
                        "age_group": "U14",
                        "division": "Northeast",
                        "date_range": "2025-10-01 to 2025-10-31",
                    },
                }
            ]
        }


class QueueAuditEvent(AuditEvent):
    """Audit event for queue submission."""

    queue_task_id: str | None = Field(None, description="Celery task ID")
    queue_success: bool = Field(..., description="Whether queue submission succeeded")
    error_message: str | None = Field(
        None, description="Error message if submission failed"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "examples": [
                {
                    "timestamp": "2025-11-13T14:31:16.789Z",
                    "run_id": "20251113-143045-abc123",
                    "event_type": "queue_submitted",
                    "correlation_id": "100436",
                    "queue_task_id": "887795e2-12a9-4e72-ba8e-04ff29f44205",
                    "queue_success": True,
                    "error_message": None,
                    "run_metadata": {
                        "league": "Homegrown",
                        "age_group": "U14",
                        "division": "Northeast",
                    },
                }
            ]
        }


class RunSummary(BaseModel):
    """Summary statistics for a scraping run."""

    total_matches: int = Field(0, description="Total matches processed")
    discovered: int = Field(0, description="New matches discovered")
    updated: int = Field(0, description="Existing matches updated")
    unchanged: int = Field(0, description="Matches with no changes")
    queue_submitted: int = Field(0, description="Matches submitted to queue")
    queue_failed: int = Field(0, description="Queue submission failures")


class RunAuditEvent(AuditEvent):
    """Audit event for run start or completion."""

    summary: RunSummary | None = Field(
        None, description="Run summary (only for run_completed events)"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "examples": [
                {
                    "timestamp": "2025-11-13T14:32:20.123Z",
                    "run_id": "20251113-143045-abc123",
                    "event_type": "run_completed",
                    "correlation_id": None,
                    "run_metadata": {
                        "league": "Homegrown",
                        "age_group": "U14",
                        "division": "Northeast",
                        "date_range": "2025-10-01 to 2025-10-31",
                        "total_matches": 15,
                    },
                    "summary": {
                        "total_matches": 15,
                        "discovered": 12,
                        "updated": 3,
                        "unchanged": 0,
                        "queue_submitted": 15,
                        "queue_failed": 0,
                    },
                }
            ]
        }
