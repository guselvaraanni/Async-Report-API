import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import create_app
from app.extensions import db
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture()
def app():
    # Isolate tests from developer .env (never touch production MySQL)
    os.environ["FLASK_ENV"] = "testing"
    os.environ["ENV"] = "testing"
    os.environ["TEST_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
    os.environ.pop("DATABASE_URL", None)

    app = create_app()
    assert app.config["TESTING"] is True
    assert "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]
    with app.app_context():
        db.create_all()

        user = User(id=1, username="u1", email="u1@example.com")
        db.session.add(user)
        db.session.commit()

        # Seed transactions for export
        db.session.bulk_save_objects(
            [
                Transaction(user_id=1, amount=10.0, currency="USD", status="COMPLETED")
                for _ in range(200)
            ]
        )
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()

