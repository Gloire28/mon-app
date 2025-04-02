# app/utils/performance.py
from collections import Counter
from datetime import datetime, timedelta
from app.models import DataEntry, Location, PerformanceMetric

WEIGHTS = {
    'tite': 0.4,
    'members': 0.3,
    'submission': 0.2,
    'comments': 0.1
}

def calculate_regional_performance(region_id):
    # Récupération des données
    region = Location.query.get(region_id)
    
    # Récupérer les districts (enfants de la région)
    districts = region.children if region else []
    district_ids = [d.id for d in districts] + [region_id]
    
    # Période des 3 derniers mois
    three_months_ago = datetime.utcnow() - timedelta(days=90)
    
    # Récupérer les entrées de données pour les districts et la région
    entries = DataEntry.query.join(Location, DataEntry.location).filter(
        Location.id.in_(district_ids),
        DataEntry.date >= three_months_ago
    ).all()
    
    # Calcul des métriques de base
    total_tite = sum(float(e.tite or 0) for e in entries)
    members_data = [e.men + e.women for e in entries]
    
    # Normalisation avec valeurs par défaut réalistes
    scores = {
        'tite': min(total_tite / 1_000_000, 1.0) if total_tite else 0,
        'members': (sum(members_data) / len(members_data) / 500) if members_data else 0,  # Objectif 500 membres
        'submission': len(entries) / 12,  # 12 dimanches attendus
        'comments': sum(1 for e in entries if e.commentaire and e.commentaire.strip()) / len(entries) if entries else 0
    }
    
    # Calcul du score pondéré
    total_score = sum(WEIGHTS[k] * v * 100 for k, v in scores.items())
    
    return {
        'total_score': round(total_score, 2),
        'performance_label': get_performance_rating(total_score)[0],
        'performance_class': get_performance_rating(total_score)[1],
        'details': scores,
        'has_report': bool(entries)
    }

def get_performance_rating(score):
    if score >= 90: return ('🔥 Très bonne', 'very-good')
    elif score >= 70: return ('🟢 Bonne', 'good')
    elif score >= 50: return ('🟡 Moyenne', 'average')
    else: return ('🔴 Faible', 'poor')