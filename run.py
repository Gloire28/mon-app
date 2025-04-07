from app import create_app
from config import DevelopmentConfig

app = create_app(DevelopmentConfig)

# Ajouter un log pour afficher l'URI de la base de données
print(f"Base de données utilisée : {app.config['SQLALCHEMY_DATABASE_URI']}")

if __name__ == "__main__":
    app.run(port=7007, debug=True)