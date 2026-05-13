# seed_50k.py
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.transaction import Transaction
import random
import time

app = create_app()

with app.app_context():
    user = User.query.filter_by(id=2).first()
    if not user:
        print("User 2 not found. Please run the original seed script first.")
        exit()

    print("🚀 Generating 50,000 dummy transactions in memory...")
    start_time = time.time()
    
    # Create all objects in memory first (much faster)
    transactions = []
    for i in range(50000):
        transactions.append(
            Transaction(
                user_id=user.id,
                amount=round(random.uniform(10.0, 1000.0), 2),
                currency="USD",
                status="COMPLETED"
            )
        )
    
    print("💾 Bulk saving to the database. Please wait...")
    # Bulk save is significantly faster than row-by-row db.session.add()
    db.session.bulk_save_objects(transactions)
    db.session.commit()
    
    end_time = time.time()
    print(f"✅ Successfully seeded 50,000 rows in {end_time - start_time:.2f} seconds!")