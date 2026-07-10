"""Seed user 1 with ~50 sample transactions."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app
from app.extensions import db
from app.models.transaction import Transaction
from app.models.user import User

app = create_app()

with app.app_context():
    user = User.query.filter_by(id=1).first()
    if not user:
        user = User(username="test_user_1", email="test1@example.com")
        db.session.add(user)
        db.session.commit()
        print("Created User 1")

    existing_tx = Transaction.query.filter_by(user_id=user.id).count()
    if existing_tx > 0:
        print(f"User 1 already has {existing_tx} transactions.")
    else:
        print("Generating 50 dummy transactions for User 1...")
        for _ in range(50):
            db.session.add(
                Transaction(
                    user_id=user.id,
                    amount=round(random.uniform(10.0, 500.0), 2),
                    currency="USD",
                    status="COMPLETED",
                )
            )
        db.session.commit()
        print("Successfully seeded 50 transactions!")
