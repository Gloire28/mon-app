def test_app_creation():
    from run import app
    assert app is not None
    assert app.config['SQLALCHEMY_DATABASE_URI'] is not None