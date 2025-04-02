# app/models.py
from datetime import datetime
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
    status = db.Column(db.String(20), default='pending_data_entry')
    reason = db.Column(db.String(200))  # Augmenté de 50 à 200 caractères
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='change_requests')
    new_region = db.relationship('Location', foreign_keys=[new_region_id])
    new_district = db.relationship('Location', foreign_keys=[new_district_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_data_entry', 'pending_team_lead', 'accepted', 'rejected')",
            name='check_change_request_status'
        ),
    )

    def __repr__(self):
        return f"<ChangeRequest {self.id} - {self.status}>"
    
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