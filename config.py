import os
from pathlib import Path

class Config:
    # Sécurité
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    
    # Configuration base de données
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = Path(__file__).resolve().parent.parent
    
    # Configuration Celery
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    CELERY_TIMEZONE = 'Africa/Lome'

    @classmethod
    def init_app(cls, app):
        # Configuration prioritaire pour les variables d'environnement
        if os.environ.get('SQLALCHEMY_DATABASE_URI'):
            app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['SQLALCHEMY_DATABASE_URI']
        # Configuration pour GitHub Actions
        elif os.environ.get('GITHUB_ACTIONS') == 'true':
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/test.db'
            cls._ensure_db_file(app)
        # Configuration par défaut
        elif not app.config.get('SQLALCHEMY_DATABASE_URI'):
            DB_PATH = cls.BASEDIR / 'instance' / 'app.db'
            app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH.as_posix()}'
            cls._ensure_db_file(app)

    @classmethod
    def _ensure_db_file(cls, app):
        """Crée le fichier de base de données si inexistant"""
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri[10:]  # Enlève 'sqlite:///'
            instance_dir = os.path.dirname(db_path)
            if instance_dir:
                os.makedirs(instance_dir, exist_ok=True)
            Path(db_path).touch(exist_ok=True)
            os.chmod(db_path, 0o664)

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://') or 'sqlite:///instance/prod.db'

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/dev.db'

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'