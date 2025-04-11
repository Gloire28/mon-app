from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
import os

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
    
    

def create_app(config_class=Config):
    """Factory d'application Flask"""
    app = Flask(__name__)
    
    # 1. Chargement de la configuration
    app.logger.info("Chargement de la configuration...")
    app.config.from_object(config_class)
    
    # Configuration spécifique pour GitHub Actions (CI)
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/runner/work/mon-app/mon-app/instance/test.db'
        app.logger.info("Mode CI GitHub Actions détecté - Configuration spéciale appliquée")
    else:
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialisation dynamique de la configuration
    config_class.init_app(app)
    
    # Log pour confirmer la base de données utilisée
    app.logger.info(f"Base de données utilisée : {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # 2. Initialisation des extensions
    app.logger.info("Initialisation de Flask-SQLAlchemy...")
    db.init_app(app)
    
    app.logger.info("Initialisation de Flask-Login...")
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'info'
    
    app.logger.info("Initialisation de Flask-Migrate...")
    migrate.init_app(app, db)
    
    # 3. Configuration des filtres Jinja2
    app.logger.info("Enregistrement des filtres template...")
    app.jinja_env.filters['format_number'] = format_number
    
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
    app.logger.info("Enregistrement des blueprints...")
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.team_lead import team_lead_bp
    from app.routes.data import data_bp
    from app.routes.data_viewer import data_viewer_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(team_lead_bp, url_prefix='/team_lead')
    app.register_blueprint(data_bp)
    app.register_blueprint(data_viewer_bp)
    
    # 6. Initialisation de la base de données avec vérification
    with app.app_context():
        app.logger.info("Vérification des modèles de base de données...")
        try:
            if not app.config.get('SQLALCHEMY_DATABASE_URI'):
                raise RuntimeError("Configuration de base de données manquante!")
                
            db.create_all()
            app.logger.info("Modèles de base de données vérifiés")
        except Exception as e:
            app.logger.critical(f"Erreur d'initialisation de la base: {str(e)}")
            raise
    
    # 7. Configuration du user loader avec logging
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        user = User.query.get(int(user_id))
        if user:
            app.logger.debug(f"Utilisateur chargé: {user.id}")
        else:
            app.logger.warning(f"Utilisateur introuvable: {user_id}")
        return user
    
    app.logger.info("Application initialisée avec succès")
    return app