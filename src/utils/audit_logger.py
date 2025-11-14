"""
Audit logger for tracking match processing activity.

Writes JSONL (JSON Lines) audit logs with daily file rotation.
"""

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from src.models.audit import (
    EventType,
    MatchAuditEvent,
    QueueAuditEvent,
    RunAuditEvent,
    RunMetadata,
    RunSummary,
)
from src.utils.logger import get_logger

logger = get_logger()


class AuditLogger:
    """
    Audit logger that writes JSONL files with daily rotation.

    Each audit entry is written as a single-line JSON object. Files are
    rotated daily based on UTC date.
    """

    def __init__(self, run_id: str, run_metadata: RunMetadata | None = None):
        """
        Initialize audit logger.

        Args:
            run_id: Unique identifier for this scraping run
            run_metadata: Metadata about the scraping run
        """
        self.run_id = run_id
        self.run_metadata = run_metadata
        self._lock = Lock()
        self._audit_dir = self._get_audit_directory()
        self._ensure_directory_exists()

    def _get_audit_directory(self) -> Path:
        """
        Get the audit log directory path.

        Checks for Kubernetes path first, falls back to local development path.

        Returns:
            Path to audit directory
        """
        k8s_path = Path("/var/log/scraper/audit")
        local_path = Path("./audit")

        # Use K8s path if it exists or can be created
        if k8s_path.parent.exists():
            return k8s_path

        # Otherwise use local development path
        return local_path

    def _ensure_directory_exists(self) -> None:
        """Create audit directory and state subdirectory if they don't exist."""
        try:
            self._audit_dir.mkdir(parents=True, exist_ok=True)
            (self._audit_dir / ".state").mkdir(exist_ok=True)
            logger.info(
                "Audit directory initialized",
                extra={"audit_dir": str(self._audit_dir)},
            )
        except Exception as e:
            logger.error(
                f"Failed to create audit directory: {e}",
                extra={"audit_dir": str(self._audit_dir), "error": str(e)},
            )
            raise

    def _get_current_log_file(self) -> Path:
        """
        Get the current log file path based on UTC date.

        Returns:
            Path to current audit log file
        """
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self._audit_dir / f"match-audit-{date_str}.jsonl"

    def _write_event(self, event_dict: dict[str, Any]) -> None:
        """
        Write an audit event to the current log file.

        Args:
            event_dict: Event data as dictionary (already serialized)
        """
        log_file = self._get_current_log_file()

        with self._lock:
            try:
                with open(log_file, "a") as f:
                    json.dump(event_dict, f, default=str)
                    f.write("\n")
            except Exception as e:
                logger.error(
                    "Failed to write audit event",
                    extra={
                        "error": str(e),
                        "log_file": str(log_file),
                        "event_type": event_dict.get("event_type"),
                    },
                )
                raise

    def log_run_started(self) -> None:
        """Log the start of a scraping run."""
        event = RunAuditEvent(
            run_id=self.run_id,
            event_type=EventType.RUN_STARTED,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))
        logger.info(
            "Audit: Run started",
            extra={
                "run_id": self.run_id,
                "league": self.run_metadata.league if self.run_metadata else None,
            },
        )

    def log_run_completed(self, summary: RunSummary) -> None:
        """
        Log the completion of a scraping run.

        Args:
            summary: Summary statistics for the run
        """
        event = RunAuditEvent(
            run_id=self.run_id,
            event_type=EventType.RUN_COMPLETED,
            run_metadata=self.run_metadata,
            summary=summary,
        )
        self._write_event(event.model_dump(mode="json"))
        logger.info(
            "Audit: Run completed",
            extra={
                "run_id": self.run_id,
                "total_matches": summary.total_matches,
                "discovered": summary.discovered,
                "updated": summary.updated,
            },
        )

    def log_match_discovered(
        self, correlation_id: str, match_data: dict[str, Any]
    ) -> None:
        """
        Log a new match discovery.

        Args:
            correlation_id: Match ID for correlation
            match_data: Complete match data
        """
        event = MatchAuditEvent(
            run_id=self.run_id,
            event_type=EventType.MATCH_DISCOVERED,
            correlation_id=correlation_id,
            match_data=match_data,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))

    def log_match_updated(
        self,
        correlation_id: str,
        match_data: dict[str, Any],
        changes: dict[str, dict[str, Any]],
    ) -> None:
        """
        Log a match update.

        Args:
            correlation_id: Match ID for correlation
            match_data: Complete match data (current state)
            changes: Field-level changes
        """
        event = MatchAuditEvent(
            run_id=self.run_id,
            event_type=EventType.MATCH_UPDATED,
            correlation_id=correlation_id,
            match_data=match_data,
            changes=changes,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))

    def log_match_unchanged(
        self, correlation_id: str, match_data: dict[str, Any]
    ) -> None:
        """
        Log an unchanged match (for tracking purposes).

        Args:
            correlation_id: Match ID for correlation
            match_data: Complete match data
        """
        event = MatchAuditEvent(
            run_id=self.run_id,
            event_type=EventType.MATCH_UNCHANGED,
            correlation_id=correlation_id,
            match_data=match_data,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))

    def log_queue_submitted(self, correlation_id: str, task_id: str) -> None:
        """
        Log successful queue submission.

        Args:
            correlation_id: Match ID for correlation
            task_id: Celery task ID
        """
        event = QueueAuditEvent(
            run_id=self.run_id,
            event_type=EventType.QUEUE_SUBMITTED,
            correlation_id=correlation_id,
            queue_task_id=task_id,
            queue_success=True,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))

    def log_queue_failed(self, correlation_id: str, error_message: str) -> None:
        """
        Log failed queue submission.

        Args:
            correlation_id: Match ID for correlation
            error_message: Error message describing the failure
        """
        event = QueueAuditEvent(
            run_id=self.run_id,
            event_type=EventType.QUEUE_FAILED,
            correlation_id=correlation_id,
            queue_task_id=None,
            queue_success=False,
            error_message=error_message,
            run_metadata=self.run_metadata,
        )
        self._write_event(event.model_dump(mode="json"))

    def get_state_file_path(self) -> Path:
        """
        Get the path to the state file for change detection.

        Returns:
            Path to last-run-state.json
        """
        return self._audit_dir / ".state" / "last-run-state.json"

    def get_audit_directory(self) -> Path:
        """
        Get the audit directory path.

        Returns:
            Path to audit directory
        """
        return self._audit_dir
