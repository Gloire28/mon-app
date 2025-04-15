from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
import os
from pathlib import Path
from datetime import datetime  # Ajouté pour le filtre datetimeformat

# Initialisation des extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def format_number(value):
    """Formate un nombre avec des séparateurs de milliers."""
    try:
        return "{:,.2f}".format(float(value)).replace(",", " ")
    except (ValueError, TypeError):
        return value

def datetimeformat(value, format='%d/%m/%Y %H:%M'):
    """Formate une date/heure selon le format spécifié."""
    if not isinstance(value, datetime):
        return value
    return value.strftime(format)

def create_app(config_class=Config):
    """Factory d'application Flask"""
    app = Flask(__name__)
    
    # 1. Chargement de la configuration
    app.config.from_object(config_class)
    
    # Configuration pour les uploads
    BASE_DIR = Path(__file__).resolve().parent.parent
    UPLOAD_FOLDER = BASE_DIR / 'app' / 'static' / 'uploads' / 'messages'
    app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'mp4'}
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 Mo maximum

    # Créer le dossier uploads/messages s'il n'existe pas
    try:
        UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        app.logger.info(f"Dossier des uploads créé : {app.config['UPLOAD_FOLDER']}")
    except Exception as e:
        app.logger.error(f"Erreur lors de la création du dossier uploads : {str(e)}")
        raise
    
    # Configuration spécifique pour GitHub Actions (CI)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialisation dynamique de la configuration
    config_class.init_app(app)
    
    # 2. Initialisation des extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'info'
    migrate.init_app(app, db)
    
    # 3. Configuration des filtres Jinja2
    app.jinja_env.filters['format_number'] = format_number
    app.jinja_env.filters['datetimeformat'] = datetimeformat  # Ajout du filtre datetimeformat
    
    # 4. Gestion des erreurs
    @app.errorhandler(404)
    def page_not_found(e):
        app.logger.error(f"Erreur 404: {e}")
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden(e):
        app.logger.error(f"Erreur 403: {e}")
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Erreur 500: {e}")
        return render_template('errors/500.html'), 500
    
    # 5. Enregistrement des Blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.team_lead import team_lead_bp
    from app.routes.data import data_bp
    from app.routes.data_viewer import data_viewer_bp
    from app.routes.messages import messages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(team_lead_bp, url_prefix='/team_lead')
    app.register_blueprint(data_bp)
    app.register_blueprint(data_viewer_bp)
    app.register_blueprint(messages_bp)
    
    # 6. Configuration du user loader
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        user = User.query.get(int(user_id))
        if not user:
            app.logger.warning(f"Utilisateur introuvable: {user_id}")
        return user
    
    return app