"""Seed user 2 with 50,000 transactions for large export demos."""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app
from app.extensions import db
from app.models.transaction import Transaction
from app.models.user import User

app = create_app()

with app.app_context():
    user = User.query.filter_by(username="test_user_2").first()
    if not user:
        user = User(username="test_user_2", email="test2@example.com")
        db.session.add(user)
        db.session.commit()
        print("Created User 2")

    existing = Transaction.query.filter_by(user_id=user.id).count()
    if existing >= 50000:
        print(f"User 2 already has {existing} transactions.")
        raise SystemExit(0)

    print("Generating 50,000 dummy transactions in memory...")
    start_time = time.time()

    transactions = [
        Transaction(
            user_id=user.id,
            amount=round(random.uniform(10.0, 1000.0), 2),
            currency="USD",
            status="COMPLETED",
        )
        for _ in range(50000)
    ]

    print("Bulk saving to the database. Please wait...")
    db.session.bulk_save_objects(transactions)
    db.session.commit()

    elapsed = time.time() - start_time
    print(f"Successfully seeded 50,000 rows in {elapsed:.2f} seconds!")
