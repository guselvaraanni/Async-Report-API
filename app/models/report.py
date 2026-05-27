from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Optional

from app.extensions import db


class Report(db.Model):
    """Report model for tracking async export jobs."""

    __tablename__ = "reports"

    class Status(Enum):
        QUEUED = "QUEUED"
        PROCESSING = "PROCESSING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCEL_REQUESTED = "CANCEL_REQUESTED"
        CANCELED = "CANCELED"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # External/public identifier; also used as Celery task_id
    task_id = db.Column(db.String(255), unique=True, nullable=False, index=True)

    status = db.Column(db.String(50), default=Status.QUEUED.value, index=True)

    requested_rows = db.Column(db.Integer, nullable=False, default=0)
    rows_processed = db.Column(db.Integer, default=0)
    progress_pct = db.Column(db.Float, default=0.0)

    file_path = db.Column(db.String(1000), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True, index=True)
    completed_at = db.Column(db.DateTime, nullable=True, index=True)
    cancel_requested_at = db.Column(db.DateTime, nullable=True, index=True)

    def __repr__(self):
        return f"<Report {self.task_id} - {self.status}>"

    def reports_folder(self) -> str:
        return os.environ.get("REPORTS_FOLDER") or os.path.join(os.getcwd(), "reports")

    def build_file_path(self) -> str:
        return os.path.join(self.reports_folder(), f"report_{self.task_id}.csv")

    def export_batch_size(self) -> int:
        try:
            return int(os.environ.get("EXPORT_BATCH_SIZE") or 10000)
        except Exception:
            return 10000

    def compute_progress_pct(self) -> float:
        if not self.requested_rows:
            return 0.0
        return min(100.0, (float(self.rows_processed) / float(self.requested_rows)) * 100.0)

    def duration_seconds(self) -> Optional[float]:
        if not self.started_at:
            return None
        end = self.completed_at or datetime.utcnow()
        return max(0.0, (end - self.started_at).total_seconds())

    def delete_files_best_effort(self) -> None:
        try:
            if self.file_path and os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception:
            return

    def to_dict_v1(self, api_prefix: str) -> dict:
        return {
            "id": self.task_id,
            "report_id": self.task_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "status": self.status,
            "requested_rows": self.requested_rows,
            "rows_processed": self.rows_processed,
            "progress_pct": round(self.compute_progress_pct(), 2),
            "error_message": self.error_message,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cancel_requested_at": self.cancel_requested_at.isoformat() if self.cancel_requested_at else None,
            "duration_seconds": self.duration_seconds(),
            "links": {
                "self": f"{api_prefix}/reports/{self.task_id}",
                "status": f"{api_prefix}/reports/{self.task_id}/status",
                "download": f"{api_prefix}/reports/{self.task_id}/download",
                "cancel": f"{api_prefix}/reports/{self.task_id}/cancel",
                "retry": f"{api_prefix}/reports/{self.task_id}/retry",
            },
        }

    def to_status_v1(self, api_prefix: str) -> dict:
        return self.to_dict_v1(api_prefix)

