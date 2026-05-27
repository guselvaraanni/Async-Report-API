from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()

# Keep disabled-by-default. Enable via config / env when needed.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
