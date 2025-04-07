# app/models.py
from datetime import datetime

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    new_region_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    new_district_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    
    # Statut amélioré avec workflow clair
    status = db.Column(db.String(20), default='pending_data_entry')
    reason = db.Column(db.String(200), nullable=True)  # Raison du rejet
    
    # Timestamps
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    responded_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Références aux validateurs
    current_data_entry_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    team_lead_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relations
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('change_requests', lazy='dynamic'))
    new_region = db.relationship('Location', foreign_keys=[new_region_id])
    new_district = db.relationship('Location', foreign_keys=[new_district_id])
    
    # Relations pour les validateurs
    current_data_entry = db.relationship(
        'User', 
        foreign_keys=[current_data_entry_id],
        backref=db.backref('pending_change_requests_to_validate', lazy='dynamic')
    )
    
    team_lead = db.relationship(
        'User',
        foreign_keys=[team_lead_id],
        backref=db.backref('team_lead_change_requests', lazy='dynamic')
    )
    
    # Contraintes
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_data_entry', 'pending_team_lead', 'accepted', 'rejected')",
            name='check_change_request_status'
        ),
        CheckConstraint(
            "(status IN ('pending_data_entry') AND current_data_entry_id IS NOT NULL) OR "
            "(status IN ('pending_team_lead') AND team_lead_id IS NOT NULL) OR "
            "(status IN ('accepted', 'rejected'))",
            name='check_validator_assignment'
        ),
        CheckConstraint(
            "responded_at IS NULL OR responded_at >= requested_at",
            name='check_response_timing'
        )
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Déterminer automatiquement le statut initial
        if not self.status:
            self.status = 'pending_team_lead' if not self.current_data_entry_id else 'pending_data_entry'

    def accept_by_data_entry(self):
        """Transition lorsque le Data Entry accepte la demande"""
        if self.status != 'pending_data_entry':
            raise ValueError("Seules les demandes pending_data_entry peuvent être acceptées par un Data Entry")
        
        # Validation de la hiérarchie région/district
        if self.new_district_id:
            district = Location.query.get(self.new_district_id)
            if not district or district.parent_id != self.new_region_id:
                raise ValueError("Incohérence région/district")
        
        # Trouver le Team Lead de la nouvelle région
        team_lead = User.query.filter_by(
            role='team_lead',
            location_id=self.new_region_id
        ).first()
        
        if not team_lead:
            raise ValueError(f"Aucun Team Lead trouvé pour la région ID {self.new_region_id}")
        
        # Transition d'état
        self.status = 'pending_team_lead'
        self.team_lead_id = team_lead.id
        self.responded_at = datetime.utcnow()

        # Persistance avec gestion d'erreur
        try:
            db.session.commit()
            current_app.logger.info(
                f"Demande {self.id} - Transition à pending_team_lead réussie. "
                f"Team Lead ID: {team_lead.id}, District ID: {self.new_district_id}"
            )
            return True
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Erreur DB sur demande {self.id}: {str(e)}",
                exc_info=True
            )
        raise ValueError("Erreur système lors de la mise à jour de la demande")
        
        # Mise à jour du statut
        self.status = 'pending_team_lead'
        self.team_lead_id = team_lead.id
        self.responded_at = datetime.utcnow()
        
        # Persistance en base de données
        db.session.commit()
        
        # Journalisation
        current_app.logger.info(
            f"Demande {self.id} acceptée par Data Entry, "
            f"transférée à Team Lead {team_lead.name}"
        )

    def reject_by_data_entry(self, reason):
        """Transition lorsque le Data Entry rejette la demande"""
        if self.status != 'pending_data_entry':
            raise ValueError("Seules les demandes pending_data_entry peuvent être rejetées par un Data Entry")
        
        if not reason or len(reason) < 10:
            raise ValueError("La raison doit contenir au moins 10 caractères")
        
        self.status = 'rejected'
        self.reason = reason
        self.responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        
        db.session.commit()

    def accept_by_team_lead(self):
        """Transition lorsque le Team Lead accepte la demande"""
        if self.status != 'pending_team_lead':
            raise ValueError("Seules les demandes pending_team_lead peuvent être acceptées par un Team Lead")
        
        # Validation de la hiérarchie
        if self.new_district_id:
            if not Location.query.get(self.new_district_id):
                raise ValueError("District invalide")
        
        self.status = 'accepted'
        self.responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        
        # Mettre à jour la localisation de l'utilisateur
        self.user.location_id = self.new_district_id or self.new_region_id
        db.session.commit()

    def reject_by_team_lead(self, reason):
        """Transition lorsque le Team Lead rejette la demande"""
        if self.status != 'pending_team_lead':
            raise ValueError("Seules les demandes pending_team_lead peuvent être rejetées par un Team Lead")
        
        if not reason or len(reason) < 10:
            raise ValueError("La raison doit contenir au moins 10 caractères")
        
        self.status = 'rejected'
        self.reason = reason
        self.responded_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        
        db.session.commit()

    def get_status_display(self):
        """Retourne la version lisible du statut"""
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