import os
from pathlib import Path

class Config:
    # Sécurité
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    
    # Configuration base de données
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuration Celery
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    CELERY_TIMEZONE = 'Africa/Lome'

    @classmethod
    def init_app(cls, app):
        # Configuration spécifique pour GitHub Actions
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
            try:
                Path('/tmp/test.db').touch()
            except Exception as e:
                app.logger.error(f"Failed to create database file: {e}")
        else:
            # Configuration pour le développement local
            BASEDIR = Path(__file__).resolve().parent.parent
            DB_PATH = BASEDIR / 'instance' / 'app.db'
            app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH.as_posix()}'
            
            # Création du dossier instance si inexistant
            instance_path = cls.BASEDIR / 'instance'
            instance_path.mkdir(exist_ok=True, mode=0o755)
            cls.DB_PATH.touch(exist_ok=True)
            os.chmod(cls.DB_PATH, 0o664)

class ProductionConfig(Config):
    # Configuration pour la production (à adapter)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://') or 'sqlite:///instance/prod.db'

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'