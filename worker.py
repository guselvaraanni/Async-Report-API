"""
Celery worker entry point.
Run with: celery -A worker.celery worker --loglevel=info
"""
from app import create_app
from app.celery_app import make_celery

app = create_app()
celery = make_celery(app)

if __name__ == '__main__':
    celery.start()
