import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")  # Ajoute la racine du projet au chemin

def test_app_creation():
    from run import app
    assert app is not None
    assert app.config['SQLALCHEMY_DATABASE_URI'] is not None