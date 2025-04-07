import os
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = Path(__file__).resolve().parent.parent
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{BASEDIR / "your_database.db"}'  # Modifiez ici

    @classmethod
    def init_app(cls, app):
        """Initialisation de l'application avec création du fichier de base de données si nécessaire"""
        db_path = Path(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch(mode=0o666, exist_ok=True)  # Permissions read/write pour tous
        app.logger.info(f"Fichier de base de données vérifié/créé : {db_path}")

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace(
        'postgres://', 'postgresql://') or f'sqlite:///{Config.BASEDIR / "instance" / "prod.db"}'

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{Config.BASEDIR / "your_database.db"}'  # Modifiez ici

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'