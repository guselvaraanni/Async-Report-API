import os
import csv
from datetime import datetime
from app.extensions import db
from app.models.report import Report
from app.models.transaction import Transaction

# Notice: All Celery imports and decorators (@celery.task) have been completely removed!

def export_transactions_task(task_id, user_id, rows):
    """
    Background task to generate a CSV report of user transactions.
    This now runs safely via native Python threading.
    """
    try:
        # 1. Get the pending report from the database
        report = Report.query.filter_by(task_id=task_id).first()
        if not report:
            print(f"Error: Report {task_id} not found in database.")
            return

        # 2. Mark as processing
        report.status = 'PROCESSING'
        report.started_at = datetime.utcnow()
        db.session.commit()

        # 3. Ensure the target directory exists (Crucial for Windows!)
        os.makedirs(os.path.dirname(f'/tmp/reports/'), exist_ok=True)
        file_path = f'/tmp/reports/report_{task_id}.csv'

        # 4. Fetch the requested data
        # We use limit(rows) to respect the amount requested by the user
        transactions = Transaction.query.filter_by(user_id=user_id).limit(rows).all()

        # 5. Open the file and write the CSV
        processed = 0
        with open(file_path, 'w', newline='') as csvfile:
            fieldnames = ['id', 'user_id', 'amount', 'currency', 'status', 'created_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for tx in transactions:
                writer.writerow({
                    'id': tx.id,
                    'user_id': tx.user_id,
                    'amount': tx.amount,
                    'currency': tx.currency,
                    'status': tx.status,
                    'created_at': tx.created_at.isoformat() if tx.created_at else ''
                })
                processed += 1
                
                # Periodically update the database so the frontend can show a progress bar
                if processed % 1000 == 0:
                    report.rows_processed = processed
                    db.session.commit()

        # 6. Finalize the report
        report.status = 'COMPLETED'
        report.rows_processed = processed
        report.file_url = f'/reports/download/{task_id}' 
        report.completed_at = datetime.utcnow()
        db.session.commit()

        print(f"Task {task_id} COMPLETED successfully! Wrote {processed} rows.")

    except Exception as e:
        # If ANYTHING goes wrong, catch it safely so the thread doesn't die silently
        print(f"Task {task_id} FAILED: {str(e)}")
        report = Report.query.filter_by(task_id=task_id).first()
        if report:
            report.status = 'FAILED'
            report.error_message = str(e)
            db.session.commit()