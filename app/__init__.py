# app/__init__.py
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config

# Définir les extensions globales
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# Définir le filtre format_number
def format_number(value):
    """Formate un nombre avec des séparateurs de milliers."""
    try:
        # Convertir en float et formater avec des virgules comme séparateurs de milliers
        return "{:,.2f}".format(float(value)).replace(",", ",")
    except (ValueError, TypeError):
        return value

def create_app(config_class=Config):
    """
    Crée et configure une instance de l'application Flask.

    Args:
        config_class: La classe de configuration à utiliser (par défaut : Config).

    Returns:
        Flask: L'application Flask configurée.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialisation des extensions
    app.logger.info("Initialisation de Flask-SQLAlchemy...")
    db.init_app(app)
    app.logger.info("Flask-SQLAlchemy initialisé avec succès.")
    
    app.logger.info("Initialisation de Flask-Login...")
    login_manager.init_app(app)
    app.logger.info("Flask-Login initialisé avec succès.")
    
    app.logger.info("Initialisation de Flask-Migrate...")
    migrate.init_app(app, db)
    app.logger.info("Flask-Migrate initialisé avec succès.")

    # Enregistrement du filtre personnalisé
    app.logger.info("Enregistrement du filtre format_number...")
    app.jinja_env.filters['format_number'] = format_number
    app.logger.info("Filtre format_number enregistré avec succès.")

    # Configuration de LoginManager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'info'

    # Gestionnaires d'erreurs
    @app.errorhandler(404)
    def page_not_found(e):
        """Gère les erreurs 404 (page non trouvée)."""
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        """Gère les erreurs 403 (accès interdit)."""
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        """Gère les erreurs 500 (erreur interne du serveur)."""
        return render_template('errors/500.html'), 500

    # Enregistrement des blueprints
    app.logger.info("Enregistrement des blueprints...")
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.team_lead import team_lead_bp
    from app.routes.data import data_bp
    from app.routes.data_viewer import data_viewer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(team_lead_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(data_viewer_bp)
    app.logger.info("Blueprints enregistrés avec succès.")

    # Initialisation de la base de données
    app.logger.info("Création des tables de la base de données...")
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Tables créées avec succès.")
        except Exception as e:
            app.logger.error(f"Erreur lors de la création des tables : {e}")
            raise

    # Loader utilisateur pour Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        """Charge un utilisateur à partir de son ID pour Flask-Login."""
        app.logger.debug(f"Chargement de l'utilisateur avec ID {user_id}")
        from app.models import User
        return User.query.get(int(user_id))

    return app