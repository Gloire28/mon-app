import os
from app import create_app, db
from app.models import User, Location, TeamMembership  # Importez vos modèles
from werkzeug.security import generate_password_hash

def seed_database():
    # Créer l'application et le contexte
    app = create_app()
    with app.app_context():
        # Supprimer toutes les données existantes
        db.drop_all()
        db.create_all()

        # Créer des localisations
        region = Location(code="REG001", name="Région Maritime", type="REG")
        district = Location(code="DIS001", name="District Lomé", type="DIS", parent=region)

        # Créer des utilisateurs
        admin = User(
            name="Admin Test",
            matriculate="ADM001",
            phone="+22890123456",
            password=generate_password_hash("admin123"), # Le mot de passe sera hashé automatiquement
            role="team_lead",
            location=region
        )

        user1 = User(
            name="Utilisateur Test",
            matriculate="USER001",
            phone="+22870123456",
            password=generate_password_hash("user123"),
            role="data_entry",
            location=district
        )

        # Créer une relation d'équipe
        membership = TeamMembership(team_lead=admin, location=region)

        # Ajouter les objets à la session
        db.session.add_all([region, district, admin, user1, membership])

        # Sauvegarder en base de données
        db.session.commit()

        print("Base de données peuplée avec succès !")

if __name__ == "__main__":
    seed_database()
