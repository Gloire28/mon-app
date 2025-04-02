# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.forms import RegistrationForm, LoginForm
from app import db
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    with current_app.app_context():  # Ajouter un contexte explicite pour charger les localisations
        form.load_locations()
    
    if form.validate_on_submit():
        with current_app.app_context():  # Contexte pour les opérations de base de données
            hashed_password = generate_password_hash(form.password.data)
            user = User(
                name=form.name.data,
                matriculate=form.matriculate.data,
                phone=form.phone.data,
                password=hashed_password,
                role=form.role.data,
                location_id=form.location.data
            )
            db.session.add(user)
            db.session.commit()
        flash('Inscription réussie ! Veuillez vous connecter.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        with current_app.app_context():  # Contexte pour la requête
            user = User.query.filter_by(matriculate=form.matriculate.data).first()
            if user and check_password_hash(user.password, form.password.data):
                login_user(user)
                next_page = request.args.get('next')
                flash('Connexion réussie !', 'success')
                return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
            else:
                flash('Matricule ou mot de passe incorrect.', 'danger')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))