from celery import Celery
from app import create_app
from app.extensions import db # type: ignore
from app.models import Location, PerformanceMetric # type: ignore
from datetime import datetime
from app.utils.performance import calculate_performance # type: ignore

def make_celery(app=None):
    app = app or create_app()
    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config['CELERY_RESULT_BACKEND']
    )
    celery.conf.update(app.config)
    celery.conf.update(task_always_eager=False)
    return celery

celery = make_celery()

@celery.task(name='update_performance_metrics')
def update_metrics():
    app = create_app()
    with app.app_context():
        regions = Location.query.filter_by(type='REG').all()
        for region in regions:
            performance = calculate_performance(region.id)
            
            metric = PerformanceMetric(
                region_id=region.id,
                score=performance['total'],
                created_at=datetime.utcnow()
            )
            db.session.add(metric)
        
        db.session.commit()
        app.logger.info(f'Métriques mises à jour à {datetime.utcnow()}')