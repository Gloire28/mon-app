from .extensions import db # type: ignore
from datetime import datetime

class PerformanceMetric(db.Model):
    __tablename__ = 'performance_metrics'
    id = db.Column(db.Integer, primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    score = db.Column(db.Float)  # Changed from individual scores
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
