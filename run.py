import os
from app import create_app
from config import DevelopmentConfig, ProductionConfig, TestingConfig
from os import environ

# Choisir la configuration en fonction de FLASK_ENV
env = environ.get('FLASK_ENV', 'development')
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}
config_class = config_map.get(env, DevelopmentConfig)  # Par défaut : DevelopmentConfig

# Créer l'application avec un static_folder explicite
app = create_app(config_class)

# Vérifier que le dossier static existe
static_folder = os.path.join(app.root_path, 'static')
if not os.path.exists(static_folder):
    app.logger.error(f"Le dossier static n'existe pas à l'emplacement : {static_folder}")
else:
    app.logger.info(f"Dossier static trouvé à : {static_folder}")

# S'assurer que Flask utilise le bon dossier static
app.static_folder = static_folder
app.static_url_path = '/static'

# Initialiser la base de données
config_class.init_app(app)

# Afficher l'URI de la base de données
app.logger.info(f"Base de données utilisée : {app.config['SQLALCHEMY_DATABASE_URI']}")

if __name__ == "__main__":
    port = int(environ.get('PORT', 7007))  # Port configurable via env, défaut 7007
    app.run(host='0.0.0.0', port=port, debug=(env == 'development'))