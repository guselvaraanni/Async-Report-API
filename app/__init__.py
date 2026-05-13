from flask import Flask
from celery import Celery
from flasgger import Swagger
from app.extensions import db

# 1. Initialize globals OUTSIDE the factory so worker.py can import them
celery = Celery(__name__)
swagger = Swagger()

def create_app():
    """Application factory."""
    app = Flask(__name__)
    
    # Using the string path is safer to avoid circular imports
    app.config.from_object('app.config.Config')

    # 2. Initialize Extensions
    db.init_app(app)
    swagger.init_app(app)

    # 3. Configure Celery to use Flask's app context
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
                
    celery.Task = ContextTask

    # 4. Register blueprints
    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    # 5. Create tables (only creates them if they don't exist)
    with app.app_context():
        db.create_all()

    return app


def init_celery(app):
    """Initialize Celery with Flask app context."""
    celery = Celery(app.import_name)
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
