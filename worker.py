"""
Celery worker entry point.
Run with: celery -A worker.celery worker --loglevel=info
"""
from app import create_app
from celery import Celery

app = create_app()
celery = Celery(app.import_name)
celery.conf.update(app.config)

# Import all tasks to register them
from app.tasks import export_transactions_task, dummy_task

if __name__ == '__main__':
    celery.start()
