# config.py
import os
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = Path(__file__).resolve().parent.parent
    if os.getenv('DATABASE_URL'):
        SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace("postgres://", "postgresql://", 1)
    else:
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{BASEDIR / "instance" / "your_database.db"}'
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        """Initialisation sécurisée de la base de données"""
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite:///'):
            db_path = Path(db_uri.replace('sqlite:///', ''))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch(mode=0o644, exist_ok=True)
            app.logger.info(f"Base de données SQLite initialisée : {db_path}")

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://') or Config.SQLALCHEMY_DATABASE_URI

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'