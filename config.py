import os
from pathlib import Path

class Config:
    # Sécurité
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    
    # Configuration base de données
    BASEDIR = Path(__file__).resolve().parent.parent
    DB_PATH = BASEDIR / 'instance' / 'app.db'
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH.as_posix().replace(" ", "%20")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuration Celery
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    CELERY_TIMEZONE = 'Africa/Lome'

    @classmethod
    def init_app(cls, app):
        # Création du dossier instance si inexistant
        instance_path = cls.BASEDIR / 'instance'
        instance_path.mkdir(exist_ok=True, mode=0o755)
        cls.DB_PATH.touch(exist_ok=True)
        os.chmod(cls.DB_PATH, 0o664)
