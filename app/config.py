import os
from datetime import timedelta


class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-prod'
    
    # Database
    # Change '@db:3306' to '@localhost:3306'
    # Change 'async_reports' to 'heavy_data_db' (the name you created)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:selva@localhost:3306/heavy_data_db'

    # Celery
    # Change 'redis://redis:6379/0' to 'redis://localhost:6379/0'
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
    
    # Report settings
    REPORTS_FOLDER = '/tmp/reports'
    MAX_ROWS_PER_REPORT = 1000000

    SWAGGER = {
        'title': 'Heavy Data Export API',
        'uiversion': 3,
        'openapi': '3.0.0',
        'description': 'An asynchronous API for generating massive data reports using Celery and Redis.'
    }