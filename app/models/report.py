from datetime import datetime
from app.extensions import db


class Report(db.Model):
    """Report model for tracking async export tasks."""
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_id = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), default='PENDING')  # PENDING, PROCESSING, COMPLETED, FAILED
    file_url = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    rows_processed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Report {self.task_id} - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'status': self.status,
            'file_url': self.file_url,
            'error_message': self.error_message,
            'rows_processed': self.rows_processed,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
