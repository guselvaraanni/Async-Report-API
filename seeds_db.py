# seed_db.py
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.transaction import Transaction
import random

# Initialize your Flask app context
app = create_app()

with app.app_context():
    # 1. Ensure we have a user
    user = User.query.filter_by(id=1).first()
    if not user:
        user = User(username="test_user_1", email="test1@example.com")
        db.session.add(user)
        db.session.commit()
        print("Created User 1")

    # 2. Check if transactions exist
    existing_tx = Transaction.query.filter_by(user_id=user.id).count()
    if existing_tx > 0:
        print(f"User 1 already has {existing_tx} transactions.")
    else:
        print("Generating 50 dummy transactions for User 1...")
        for i in range(50):
            tx = Transaction(
                user_id=user.id,
                amount=round(random.uniform(10.0, 500.0), 2),
                currency="USD",
                status="COMPLETED"
            )
            db.session.add(tx)
        db.session.commit()
        print("Successfully seeded 50 transactions!")