import os
import uuid
import threading
from flask import Blueprint, jsonify, request, send_file, current_app
from app.extensions import db
from app.models.user import User
from app.models.report import Report

# Reminder: Ensure @celery.task is removed from this function in export_tasks.py
from app.tasks.export_tasks import export_transactions_task 

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    ---
    tags:
      - System
    responses:
      200:
        description: API is healthy
    """
    return jsonify({'status': 'healthy'}), 200


@reports_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Request a new heavy data export.
    ---
    tags:
      - Reports
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              user_id:
                type: integer
                default: 1
                example: 1
              rows:
                type: integer
                default: 50000
                example: 50000
    responses:
      202:
        description: Task accepted and queued.
      404:
        description: User not found.
    """
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id', 1)
        rows = data.get('rows', 50000)

        print(f"Received report generation request for user_id={user_id} with rows={rows}")

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': f'User {user_id} not found'}), 404

        task_id = str(uuid.uuid4())

        report = Report(
            user_id=user_id,
            task_id=task_id,
            status='PENDING'
        )
        db.session.add(report)
        db.session.commit()

        # NATIVE PYTHON THREADING
        app = current_app._get_current_object()

        def run_background_task(app_context, t_id, u_id, r_count):
            with app_context.app_context():
                export_transactions_task(t_id, u_id, r_count)

        thread = threading.Thread(
            target=run_background_task, 
            args=(app, task_id, user_id, rows)
        )
        thread.start()

        return jsonify({
            'task_id': task_id,
            'status': 'PENDING'
        }), 202

    except Exception as e:
        print(f"CRITICAL ERROR in generate_report: {str(e)}")
        return jsonify({
            'error': 'Internal server error', 
            'details': str(e)
        }), 500


@reports_bp.route('/status/<task_id>', methods=['GET'])
def report_status(task_id):
    """
    Check the status of a report generation task.
    ---
    tags:
      - Reports
    parameters:
      - in: path
        name: task_id
        required: true
        schema:
          type: string
        description: The UUID of the task
    responses:
      200:
        description: Current status of the task.
      404:
        description: Report not found.
    """
    try:
        report = Report.query.filter_by(task_id=task_id).first()
        if not report:
            return jsonify({'error': f'Report {task_id} not found'}), 404

        response = {
            'task_id': task_id,
            'status': report.status,
            'rows_processed': report.rows_processed,
            'created_at': report.created_at.isoformat(),
            'started_at': report.started_at.isoformat() if report.started_at else None,
            'completed_at': report.completed_at.isoformat() if report.completed_at else None
        }

        if report.status == 'COMPLETED':
            response['download_url'] = f'/api/reports/download/{task_id}'
            response['file_url'] = report.file_url

        if report.status == 'FAILED':
            response['error_message'] = report.error_message

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/download/<task_id>', methods=['GET'])
def download_report(task_id):
    """
    Download the completed CSV report.
    ---
    tags:
      - Reports
    parameters:
      - in: path
        name: task_id
        required: true
        schema:
          type: string
        description: The UUID of the task.
    responses:
      200:
        description: The CSV file.
      400:
        description: Report not ready yet.
      404:
        description: Report or file not found.
    """
    try:
        report = Report.query.filter_by(task_id=task_id).first()
        if not report:
            return jsonify({'error': f'Report {task_id} not found'}), 404

        if report.status != 'COMPLETED':
            return jsonify({
                'error': f'Report not ready. Current status: {report.status}'
            }), 400

        file_path = f'/tmp/reports/report_{task_id}.csv'
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found on disk'}), 404

        return send_file(
            file_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'report_{task_id}.csv'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/list', methods=['GET'])
def list_reports():
    """
    List all reports for a user.
    ---
    tags:
      - Reports
    parameters:
      - in: query
        name: user_id
        required: false
        schema:
          type: integer
          default: 1
        description: The ID of the user to fetch reports for.
    responses:
      200:
        description: A list of reports for the user.
    """
    try:
        user_id = request.args.get('user_id', 1, type=int)
        reports = Report.query.filter_by(user_id=user_id).all()
        
        return jsonify({
            'user_id': user_id,
            'count': len(reports),
            'reports': [report.to_dict() for report in reports]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/delete/<task_id>', methods=['DELETE'])
def delete_report(task_id):
    """
    Delete a report and its associated file.
    ---
    tags:
      - Reports
    parameters:
      - in: path
        name: task_id
        required: true
        schema:
          type: string
        description: The UUID of the task to delete.
    responses:
      200:
        description: Report deleted successfully.
      404:
        description: Report not found.
    """
    try:
        report = Report.query.filter_by(task_id=task_id).first()
        if not report:
            return jsonify({'error': f'Report {task_id} not found'}), 404

        file_path = f'/tmp/reports/report_{task_id}.csv'
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(report)
        db.session.commit()

        return jsonify({'message': f'Report {task_id} deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/cancel/<task_id>', methods=['POST'])
def cancel_report(task_id):
    """
    Cancel a pending or processing report.
    ---
    tags:
      - Reports
    parameters:
      - in: path
        name: task_id
        required: true
        schema:
          type: string
        description: The UUID of the task to cancel.
    responses:
      200:
        description: Task successfully canceled.
      400:
        description: Task is already completed or failed.
      404:
        description: Report not found.
    """
    try:
        report = Report.query.filter_by(task_id=task_id).first()
        if not report:
            return jsonify({'error': f'Report {task_id} not found'}), 404

        if report.status in ['COMPLETED', 'FAILED', 'CANCELED']:
            return jsonify({
                'error': f'Cannot cancel task. Current status is {report.status}'
            }), 400
        
        report.status = 'CANCELED'
        db.session.commit()

        return jsonify({'message': f'Report {task_id} has been marked as canceled.'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@reports_bp.route('/stats', methods=['GET'])
def report_stats():
    """
    Get system-wide report statistics.
    ---
    tags:
      - System
    responses:
      200:
        description: Aggregated statistics of all reports.
    """
    try:
        total_reports = Report.query.count()
        pending = Report.query.filter_by(status='PENDING').count()
        processing = Report.query.filter_by(status='PROCESSING').count()
        completed = Report.query.filter_by(status='COMPLETED').count()
        failed = Report.query.filter_by(status='FAILED').count()
        canceled = Report.query.filter_by(status='CANCELED').count()

        return jsonify({
            'total_requests': total_reports,
            'current_queue': {
                'pending': pending,
                'processing': processing
            },
            'finished': {
                'completed': completed,
                'failed': failed,
                'canceled': canceled
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@reports_bp.route('/users', methods=['POST'])
def create_user():
    """
    Create a new user (Utility endpoint).
    ---
    tags:
      - System
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              username:
                type: string
                example: test_user
              email:
                type: string
                example: test@example.com
    responses:
      201:
        description: User created successfully.
    """
    try:
        if not request.is_json:
          return jsonify({'error': 'Content-Type must be application/json'}), 415
        
        data = request.get_json(silent=True) or {}

        username = data.get('username', 'default_user')
        email = data.get('email', f'{username}@example.com')

        new_user = User(username=username, email=email)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            'message': 'User created',
            'user_id': new_user.id,
            'username': new_user.username
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500