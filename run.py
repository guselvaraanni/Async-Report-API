"""
Main Flask application entry point.
Run with: python run.py
"""
import os
from dotenv import load_dotenv

# 1. Load the .env file FIRST so os.environ is populated
load_dotenv() 

# 2. Import the factory function
from app import create_app

# 3. Create the single, authoritative Flask instance
app = create_app()

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('FLASK_PORT', 5000)),
        debug=os.environ.get('FLASK_ENV', 'development') == 'development'
    )