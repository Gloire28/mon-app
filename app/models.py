from datetime import datetime
from typing import Self

from flask import current_app
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import CheckConstraint

# Définir d'abord les modèles sans dépendances ou avec des dépendances minimales
class Location(db.Model):
    __tablename__ = 'locations'  # Utiliser 'locations' pour correspondre aux références
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(3), nullable=False)  # 'REG' ou 'DIS'
    parent_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)

    parent = db.relationship('Location', remote_side=[id], back_populates='children')
    children = db.relationship('Location', back_populates='parent')
    users = db.relationship('User', back_populates='location')
    conversations = db.relationship('Conversation', back_populates='location')
    data_entries = db.relationship('DataEntry', back_populates='location')
    performance_metrics = db.relationship('PerformanceMetric', back_populates='region')
    change_requests = db.relationship('ChangeRequest', back_populates='target_district')
    promotion_requests = db.relationship('PromotionRequest', back_populates='requested_region')

    def __repr__(self):
        return f"<Location {self.name}>"

# Ensuite, définir User, qui dépend de Location
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    matriculate = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='data_entry')
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship('Location', back_populates='users')
    data_entries = db.relationship('DataEntry', back_populates='user')
    messages = db.relationship('Message', back_populates='sender')
    notifications = db.relationship('Notification', back_populates='user')
    change_requests_made = db.relationship('ChangeRequest', foreign_keys='ChangeRequest.requester_id', back_populates='requester', lazy='dynamic')
    exchange_requests = db.relationship('ChangeRequest', foreign_keys='ChangeRequest.exchange_with_user_id', back_populates='exchange_with')
    promotion_requests = db.relationship('PromotionRequest', back_populates='user')
    team_reports_lead = db.relationship('TeamReport', foreign_keys='TeamReport.team_lead_id', back_populates='team_lead')
    team_reports_member = db.relationship('TeamReport', foreign_keys='TeamReport.member_id', back_populates='member')

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<User {self.name}>"

# Définir DataEntry, qui dépend de User et Location
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

    user = db.relationship('User', back_populates='data_entries')
    location = db.relationship('Location', back_populates='data_entries')

    __table_args__ = (
        CheckConstraint('members = children + men + women', name='check_members_sum'),
    )

    def __repr__(self):
        return f"<DataEntry {self.id}>"

# Définir PerformanceMetric, qui dépend de Location
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

    region = db.relationship('Location', back_populates='performance_metrics')

    def __repr__(self):
        return f"<PerformanceMetric {self.id}>"

# Définir ChangeRequest, qui dépend de User et Location
class ChangeRequest(db.Model):
    __tablename__ = 'change_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_district_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    exchange_with_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='pending_data_entry', nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    data_entry_responded_at = db.Column(db.DateTime, nullable=True)
    team_lead_responded_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relations
    requester = db.relationship('User', foreign_keys=[requester_id], back_populates='change_requests_made')
    target_district = db.relationship('Location', foreign_keys=[target_district_id], back_populates='change_requests')
    exchange_with = db.relationship('User', foreign_keys=[exchange_with_user_id], back_populates='exchange_requests')
    
    # Relation pour target_region (vue uniquement)
    target_region = db.relationship(
        'Location',
        primaryjoin="and_(ChangeRequest.target_district_id == Location.id, Location.parent_id == remote(Location.id))",
        viewonly=True,
        uselist=False
    )

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
        
        district = db.session.get(Location, self.target_district_id)
        if not district or district.type != 'DIS':
            raise ValueError("Le district cible est invalide.")
        
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
        
        district = db.session.get(Location, self.target_district_id)
        if not district or district.type != 'DIS':
            raise ValueError("Le district cible est invalide.")
        
        requester = db.session.get(User, self.requester_id)
        original_district_id = requester.location_id
        
        if self.exchange_with_user_id:
            exchange_user = db.session.get(User, self.exchange_with_user_id)
            if exchange_user:
                exchange_user.location_id = original_district_id
                requester.location_id = self.target_district_id
                current_app.logger.info(f"Échange effectué : {requester.name} <-> {exchange_user.name}")
            else:
                raise ValueError("Utilisateur pour l'échange introuvable.")
        else:
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

# Définir PromotionRequest, qui dépend de User et Location
class PromotionRequest(db.Model):
    __tablename__ = 'promotion_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_region_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)

    user = db.relationship('User', back_populates='promotion_requests')
    requested_region = db.relationship('Location', back_populates='promotion_requests')

    def __repr__(self):
        return f"<PromotionRequest {self.id} - {self.status}>"

# Définir TeamReport, qui dépend de User
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

    team_lead = db.relationship('User', foreign_keys=[team_lead_id], back_populates='team_reports_lead')
    member = db.relationship('User', foreign_keys=[member_id], back_populates='team_reports_member')

    def __repr__(self):
        return f"<TeamReport {self.id}>"

# Définir Conversation, qui dépend de Location
class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # 'private' ou 'group'
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    title = db.Column(db.String(100))  # Pour le groupe global

    location = db.relationship('Location', back_populates='conversations')
    messages = db.relationship('Message', back_populates='conversation')

    # Contraintes
    __table_args__ = (
        db.CheckConstraint("type IN ('private', 'group')", name='check_conversation_type'),
    )

    def __repr__(self):
        return f"<Conversation {self.id} - {self.type}>"

# Définir Message, qui dépend de User et Conversation
class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    attachment_path = db.Column(db.String(255))
    attachment_type = db.Column(db.String(50))

    sender = db.relationship('User', back_populates='messages')
    conversation = db.relationship('Conversation', back_populates='messages')
    notifications = db.relationship('Notification', back_populates='message_rel')

    # Contraintes
    __table_args__ = (
        db.CheckConstraint(
            "attachment_type IN ('image', 'file', 'video') OR attachment_type IS NULL",
            name='check_attachment_type'
        ),
    )

    def __repr__(self):
        return f"<Message {self.id} in Conversation {self.conversation_id}>"

# Définir Notification, qui dépend de User et Message
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notification_message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'))

    user = db.relationship('User', back_populates='notifications')
    message_rel = db.relationship('Message', back_populates='notifications')

    def __repr__(self):
        return f"<Notification {self.id} for User {self.user_id}>"