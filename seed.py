import os
from app import create_app, db
from app.models import User, Location, ChangeRequest, DataEntry, PerformanceMetric, PromotionRequest, TeamReport, Notification

def seed_database():
    # Créer l'application et le contexte
    app = create_app()
    with app.app_context():
        # Supprimer toutes les données existantes
        db.drop_all()
        db.create_all()

        # Créer des localisations
        region1 = Location(code="REG001", name="Région de l'Ouest", type="REG")
        region2 = Location(code="REG002", name="Région de l'Est", type="REG")
        district1 = Location(code="DIS001", name="Lomé", type="DIS", parent=region1)
        district2 = Location(code="DIS002", name="Kara", type="DIS", parent=region1)
        district3 = Location(code="DIS003", name="Porto-Novo", type="DIS", parent=region2)
        district4 = Location(code="DIS004", name="Cotonou", type="DIS", parent=region2)

        # Créer des utilisateurs avec leurs hachages de mot de passe
        # Data Entry
        juste = User(
            name="Juste",
            matriculate="JUSTE001",
            phone="+22890123451",
            password="scrypt:32768:8:1$fLInS0PoI4nvGwi3$3d9668f373bc7e36105f4a561c91abab3fce7f898e3f331b50d39f51ee79adca48299d0389aff15455ef0d738e28ae6aaafe32b854ca7120a6c92c5f975954d7",
            role="data_entry",
            location=district1
        )
        kevine = User(
            name="Kevine",
            matriculate="KEVINE001",
            phone="+22890123452",
            password="scrypt:32768:8:1$PoutXuSILHbTNRKV$92344dd827a84e2a6b7d619bc452d5a95e11938fbdc92a5c8e2db0f02534116f7c2c703693c1453db2732dda809ffa06aea54f79c990c65e86acf47f92f3f91a",
            role="data_entry",
            location=district2
        )
        joseph = User(
            name="Joseph",
            matriculate="JOSEPH001",
            phone="+22890123453",
            password="scrypt:32768:8:1$mVVACT5yUr9k7XgV$7c2a5da1020a34d685e299d76576a5478d9afac9c12222da865a41c2a53f83c7bca215d8f9a8e501e4f998f5ecad53fe962462469b61351e585a7852b5c83d1a",
            role="data_entry",
            location=district3
        )
        gamal = User(
            name="Gamal",
            matriculate="GAMAL001",
            phone="+22890123454",
            password="scrypt:32768:8:1$MAXnKrks8EGxv2qz$8a1968b833050387f2fb9d1cf79a8c665a1a6f841335f8f8c4d7ff3eec1216d993fa9343ace164718bf54b77494d989ff847a0eb47d3b85cb0c5d5b71039b916",
            role="data_entry",
            location=district4
        )

        # Team Lead
        eme = User(
            name="Eme",
            matriculate="EME001",
            phone="+22890123455",
            password="scrypt:32768:8:1$rXHSNAbg7cIzusES$14ca65938d2b7afcb664bdfcae5193f2be79ee4e8efce253b8dbf1c84ea01229c51cd10e6bf4728e5374720cba52ee394ee968f81e14f6cf63d3dde6cc028afc",
            role="team_lead",
            location=region1
        )
        spero = User(
            name="Spero",
            matriculate="SPERO001",
            phone="+22890123456",
            password="scrypt:32768:8:1$dRqW1xwZnczlXYB4$21ac44234269876290a954337d1649917b703fbb3cd996a5069e5b5169101a6e3c1e98690623ae773694a9ff3c3c9a689a977432094a7034abc6ea0d07375547",
            role="team_lead",
            location=region2
        )

        # Data Viewer
        gloir = User(
            name="Gloir",
            matriculate="GLOIR001",
            phone="+22890123457",
            password="scrypt:32768:8:1$f7vW2y1stqN2LVxV$61fe757664d1e50c1eec3ec681eb0270bbe38cb60d7f29fedb4b3b838062d04b4ddd9ea4569d4a679ff1f4237a7d28b604b27e077bf41c0f75c369276d29ff70",
            role="data_viewer",
            location=None
        )

        # Ajouter les objets à la session
        db.session.add_all([region1, region2, district1, district2, district3, district4, juste, kevine, joseph, gamal, eme, spero, gloir])

        # Sauvegarder en base de données
        db.session.commit()

        print("Base de données peuplée avec succès !")

if __name__ == "__main__":
    seed_database()