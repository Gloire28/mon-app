# app/models.py
from datetime import datetime
from typing import Self

from flask import current_app
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import CheckConstraint

class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(4), nullable=False)  # REG ou DIS
    parent_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    children = db.relationship('Location', backref=db.backref('parent', remote_side=[id]))
    metrics = db.relationship('PerformanceMetric', backref='region', lazy='dynamic')
    
    def __repr__(self):
        return f"<Location {self.name}>"

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matriculate = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='data_entry')
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    location = db.relationship('Location', backref='users')
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    data_entries = db.relationship('DataEntry', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<User {self.name}>"

class DataEntry(db.Model):
    __tablename__ = 'data_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.Column(db.Integer, nullable=False)
    children = db.Column(db.Integer, nullable=False)
    men = db.Column(db.Integer, nullable=False)
    women = db.Column(db.Integer, nullable=False)
    tite = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    commentaire = db.Column(db.Text)
    validated = db.Column(db.Boolean, default=False)

    location = db.relationship('Location', backref='data_entries', foreign_keys=[location_id])

    __table_args__ = (
        CheckConstraint('members = children + men + women', name='check_members_sum'),
    )

    def __repr__(self):
        return f"<DataEntry {self.id}>"

class PerformanceMetric(db.Model):
    __tablename__ = 'performance_metrics'
    id = db.Column(db.Integer, primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    score = db.Column(db.Float)
    tite_score = db.Column(db.Float)
    members_score = db.Column(db.Float)
    submission_score = db.Column(db.Float)
    comment_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PerformanceMetric {self.id}>"
    

class ChangeRequest(db.Model):
    __tablename__ = 'change_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    # L'utilisateur qui fait la demande (Juste)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Le district cible demandé (Cotonou)
    target_district_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    # Statut de la demande avec un workflow clair
    status = db.Column(db.String(20), default='pending_data_entry', nullable=False)
    # Raison du rejet (optionnel)
    reason = db.Column(db.String(200), nullable=True)
    # Timestamps pour suivre le processus
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_entry_responded_at = db.Column(db.DateTime, nullable=True)
    team_lead_responded_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relations
    requester = db.relationship('User', foreign_keys=[requester_id], backref=db.backref('change_requests_made', lazy='dynamic'))
    target_district = db.relationship('Location', foreign_keys=[target_district_id])
    
    # Contraintes
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending_data_entry', 'pending_team_lead', 'accepted', 'rejected')",
            name='check_change_request_status'
        ),
        db.CheckConstraint(
            "data_entry_responded_at IS NULL OR data_entry_responded_at >= requested_at",
            name='check_data_entry_response_timing'
        ),
        db.CheckConstraint(
            "team_lead_responded_at IS NULL OR team_lead_responded_at >= data_entry_responded_at",
            name='check_team_lead_response_timing'
        )
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.status:
            self.status = 'pending_data_entry'

    def approve_by_data_entry(self):
        """Approuver la demande par le Data Entry actuel du district cible (Gamal)"""
        if self.status != 'pending_data_entry':
            raise ValueError("La demande doit être en attente de validation par le Data Entry.")
        
        # Vérifier que le district cible existe et obtenir sa région
        district = db.session.get(Location, self.target_district_id)
        if not district or district.type != 'DIS':
            raise ValueError("Le district cible est invalide.")
        
        # Passer à l'étape suivante : validation par le Team Lead
        self.status = 'pending_team_lead'
        self.data_entry_responded_at = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Demande {self.id} approuvée par le Data Entry, en attente du Team Lead.")

    def reject_by_data_entry(self, reason):
        """Rejeter la demande par le Data Entry actuel (Gamal)"""
        if self.status != 'pending_data_entry':
            raise ValueError("La demande doit être en attente de validation par le Data Entry.")
        if not reason or len(reason) < 10:
            raise ValueError("La raison du rejet doit contenir au moins 10 caractères.")
        
        self.status = 'rejected'
        self.reason = reason
        self.data_entry_responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Demande {self.id} rejetée par le Data Entry : {reason}")

    def approve_by_team_lead(self):
        """Approuver la demande par le Team Lead de la région cible (Spero)"""
        if self.status != 'pending_team_lead':
            raise ValueError("La demande doit être en attente de validation par le Team Lead.")
        
        # Vérifier le district cible
        district = db.session.get(Location, self.target_district_id)
        if not district or district.type != 'DIS':
            raise ValueError("Le district cible est invalide.")
        
        # Mettre à jour la localisation du demandeur (Juste)
        requester = db.session.get(User, self.requester_id)
        requester.location_id = self.target_district_id
        self.status = 'accepted'
        self.team_lead_responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Demande {self.id} approuvée par le Team Lead. {requester.name} assigné à {district.name}.")

    def reject_by_team_lead(self, reason):
        """Rejeter la demande par le Team Lead (Spero)"""
        if self.status != 'pending_team_lead':
            raise ValueError("La demande doit être en attente de validation par le Team Lead.")
        if not reason or len(reason) < 10:
            raise ValueError("La raison du rejet doit contenir au moins 10 caractères.")
        
        self.status = 'rejected'
        self.reason = reason
        self.team_lead_responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Demande {self.id} rejetée par le Team Lead : {reason}")

    def get_status_display(self):
        """Afficher une version lisible du statut"""
        status_map = {
            'pending_data_entry': 'En attente du Data Entry',
            'pending_team_lead': 'En attente du Team Lead',
            'accepted': 'Acceptée',
            'rejected': 'Rejetée'
        }
        return status_map.get(self.status, self.status)

    def __repr__(self):
        return f"<ChangeRequest {self.id} - {self.get_status_display()}>"
    
class PromotionRequest(db.Model):
    __tablename__ = 'promotion_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_region_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='promotion_requests')
    requested_region = db.relationship('Location', foreign_keys=[requested_region_id])

    def __repr__(self):
        return f"<PromotionRequest {self.id} - {self.status}>"

class TeamReport(db.Model):
    __tablename__ = 'team_reports'
    id = db.Column(db.Integer, primary_key=True)
    team_lead_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    member_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    performance = db.Column(db.String(50), nullable=True)
    comments = db.Column(db.Text)
    month = db.Column(db.Integer, nullable=True)
    year = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    team_lead = db.relationship('User', foreign_keys=[team_lead_id])
    member = db.relationship('User', foreign_keys=[member_id])

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f"<Notification {self.id} for User {self.user_id}>"