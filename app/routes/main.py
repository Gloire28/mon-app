from flask import Blueprint, abort, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from app.models import DataEntry, Location, User, ChangeRequest, PromotionRequest
from app.forms import DataEntryForm
from app import db
from datetime import date, datetime, timedelta
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from app.utils.performance import calculate_regional_performance

main_bp = Blueprint('main', __name__)

# Fonction utilitaire pour calculer l'intervalle de mardi à mardi
def get_tuesday_to_tuesday_interval():
    today = datetime.now()
    days_since_tuesday = (today.weekday() - 1) % 7
    start_date = today - timedelta(days=days_since_tuesday)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=6)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_date, end_date

@main_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('main/home.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        if current_user.role == 'data_entry':
            return redirect(url_for('data.dashboard'))
        elif current_user.role == 'team_lead':
            with current_app.app_context():
                if not current_user.location or current_user.location.type != 'REG':
                    flash("Aucune région valide attribuée", 'danger')
                    return render_template(
                        'team_lead/dashboard.html',
                        user_location=None,
                        metrics={'districts_count': 0, 'monthly_tite': 0.0, 'team_members': 0, 'pending_requests_count': 0},
                        pending_requests=[],
                        form=None,
                        district_entries=[],
                        district_entries_data=[]
                    )

                districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
                district_ids = [d.id for d in districts]

                team_members_count = User.query.filter(
                    User.role == 'data_entry',
                    User.location_id.in_(district_ids)
                ).count()

                districts_count = len(districts)

                current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                monthly_tite = db.session.query(db.func.sum(DataEntry.tite)).join(Location).filter(
                    Location.parent_id == current_user.location_id,
                    DataEntry.date >= current_month_start
                ).scalar() or 0.0

                pending_requests = ChangeRequest.query.options(
                    joinedload(ChangeRequest.requester),
                    joinedload(ChangeRequest.target_district),
                    joinedload(ChangeRequest.target_region),
                    joinedload(ChangeRequest.exchange_with)
                ).filter(
                    ChangeRequest.status == 'pending_team_lead',
                    ChangeRequest.target_district_id.in_(district_ids)
                ).all()

                valid_pending_requests = []
                for req in pending_requests:
                    if not req.target_district:
                        current_app.logger.warning(f"Demande {req.id} n'a pas de district cible")
                        flash(f"La demande {req.id} n'a pas de district cible.", 'warning')
                        continue
                    if not req.target_region:
                        current_app.logger.warning(f"Demande {req.id} a un district cible sans région parent : {req.target_district_id}")
                        flash(f"La demande {req.id} a un district cible sans région parent.", 'warning')
                        continue
                    if req.target_region.id != current_user.location_id:
                        current_app.logger.warning(f"Demande {req.id} cible une région ({req.target_region.id}) différente de celle du Team Lead ({current_user.location_id})")
                        flash(f"La demande {req.id} cible une région différente de la vôtre.", 'warning')
                        continue
                    valid_pending_requests.append(req)

                metrics = {
                    'districts_count': districts_count,
                    'team_members': team_members_count,
                    'monthly_tite': monthly_tite,
                    'pending_requests_count': len(valid_pending_requests)
                }

                form = DataEntryForm()
                form.load_locations(user_location_id=current_user.location_id)
                district_entries = DataEntry.query.options(
                    joinedload(DataEntry.user),
                    joinedload(DataEntry.location)
                ).filter(
                    DataEntry.location_id.in_(district_ids)
                ).order_by(DataEntry.date.desc()).limit(10).all()
                district_entries_data = [
                    {
                        'members': entry.members,
                        'tite': entry.tite if entry.tite is not None else 0,
                        'date': entry.date.strftime('%d/%m/%Y'),
                        'user': entry.user.name if entry.user else 'N/A',
                        'district': entry.location.name if entry.location else 'N/A'
                    }
                    for entry in district_entries
                ]

            return render_template(
                'team_lead/dashboard.html',
                user_location=current_user.location,
                metrics=metrics,
                pending_requests=valid_pending_requests,
                form=form,
                district_entries=district_entries,
                district_entries_data=district_entries_data
            )
        elif current_user.role == 'data_viewer':
            with current_app.app_context():
                # Vérifier si l'utilisateur a une localisation valide
                # Charger les régions
                regions = Location.query.filter_by(type='REG').all()
                regions_data = []
                for region in regions:
                    team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
                    performance = calculate_regional_performance(region.id)
                    regions_data.append({
                        'region': {
                            'id': region.id,
                            'name': region.name,
                            'type': region.type
                        },
                        'team_lead': {
                            'id': team_lead.id,
                            'name': team_lead.name
                        } if team_lead else None,
                        'performance': performance
                    })
                
                # Charger les utilisateurs
                users_data = []
                users = User.query.all()
                for user in users:
                    total_entries = DataEntry.query.filter_by(user_id=user.id).count()
                    last_entry = DataEntry.query.filter_by(user_id=user.id).order_by(DataEntry.date.desc()).first()
                    # Charger la localisation de l'utilisateur
                    location = Location.query.get(user.location_id) if user.location_id else None
                    district = location if location and location.type == 'DIS' else None
                    region = location.parent if district else (location if location and location.type == 'REG' else None)
                    users_data.append({
                        'user': {
                            'id': user.id,
                            'name': user.name,
                            'role': user.role
                        },
                        'district': district,
                        'region': region,
                        'total_entries': total_entries,
                        'last_comment': last_entry.commentaire[:20] if last_entry and last_entry.commentaire else 'Aucun'
                    })
                
                # Charger les données pour les graphiques (donut et barres)
                start_date = datetime.now() - timedelta(days=365)
                donut_data = {}  # { region_id: { role: total_entries } }
                bar_data = {}    # { region_id: { role: { total_districts: X, districts_with_entries: Y, percentage: Z } } }

                for region in regions:
                    district_ids = [loc.id for loc in Location.query.filter_by(parent_id=region.id, type='DIS').all()]
                    all_location_ids = district_ids + [region.id]
                    
                    # Charger les entrées pour la région (12 derniers mois)
                    entries = DataEntry.query.join(User).filter(
                        DataEntry.location_id.in_(all_location_ids),
                        DataEntry.date >= start_date
                    ).all()
                    
                    # Initialiser les données pour cette région
                    donut_data[region.id] = {}
                    bar_data[region.id] = {}
                    
                    # Calculer pour chaque rôle (all, team_lead, data_entry)
                    for role in ['all', 'team_lead', 'data_entry']:
                        # Graphique en donut : Total des entrées
                        total_entries = sum(
                            entry.members if entry.members is not None else 0
                            for entry in entries
                            if role == 'all' or entry.user.role == role
                        )
                        donut_data[region.id][role] = total_entries
                        
                        # Graphique en barres : Pourcentage de districts ayant soumis des données
                        total_districts = len(district_ids)
                        districts_with_entries = len(set(
                            entry.location_id for entry in entries
                            if entry.location_id in district_ids and (role == 'all' or entry.user.role == role)
                        ))
                        percentage = (districts_with_entries / total_districts * 100) if total_districts > 0 else 0
                        bar_data[region.id][role] = {
                            'total_districts': total_districts,
                            'districts_with_entries': districts_with_entries,
                            'percentage': round(percentage, 2)
                        }

                # Vérifier si donut_data contient des données significatives
                if all(all(value == 0 for value in roles.values()) for roles in donut_data.values()):
                    flash("Aucune donnée disponible pour les graphiques (dernière année).", 'info')
                
                # Charger les demandes en attente
                pending_change_requests = ChangeRequest.query.options(
                    joinedload(ChangeRequest.requester),
                    joinedload(ChangeRequest.target_district),
                    joinedload(ChangeRequest.target_region),
                    joinedload(ChangeRequest.exchange_with)
                ).filter_by(status='pending_data_entry').all()
                
                pending_promotion_requests = PromotionRequest.query.options(
                    joinedload(PromotionRequest.user),
                    joinedload(PromotionRequest.requested_region)
                ).filter_by(status='pending').all()
            
            return render_template(
                'data_viewer/dashboard.html',
                regions_data=regions_data,
                users_data=users_data,
                donut_data=donut_data,
                bar_data=bar_data,
                pending_change_requests=pending_change_requests,
                pending_promotion_requests=pending_promotion_requests
            )
        return abort(403)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Erreur SQLAlchemy dans dashboard pour l'utilisateur {current_user.id} ({current_user.role}) : {str(e)}", exc_info=True)
        flash(f"Erreur de base de données lors du chargement du tableau de bord ({current_user.role}). Contactez l'administrateur.", 'danger')
        return render_template('main/home.html')
    except TypeError as te:
        current_app.logger.error(f"Erreur de sérialisation dans dashboard pour l'utilisateur {current_user.id} ({current_user.role}) : {str(te)}", exc_info=True)
        flash(f"Erreur de données dans le tableau de bord ({current_user.role}) : format invalide. Contactez l'administrateur.", 'danger')
        return render_template('main/home.html')
    except UnboundLocalError as ule:
        current_app.logger.error(f"Erreur de variable dans dashboard pour l'utilisateur {current_user.id} ({current_user.role}) : {str(ule)}", exc_info=True)
        flash(f"Erreur de données dans le tableau de bord ({current_user.role}). Vérifiez vos entrées ou contactez l'administrateur.", 'danger')
        return render_template('main/home.html')
    except AttributeError as ae:
        current_app.logger.error(f"Erreur d'attribut dans dashboard pour l'utilisateur {current_user.id} ({current_user.role}) : {str(ae)}", exc_info=True)
        flash(f"Données invalides détectées dans le tableau de bord ({current_user.role}). Contactez l'administrateur.", 'danger')
        return render_template('main/home.html')
    except Exception as e:
        current_app.logger.error(f"Erreur inattendue dans dashboard pour l'utilisateur {current_user.id} ({current_user.role}) : {str(e)}", exc_info=True)
        flash(f"Erreur inattendue pour le tableau de bord ({current_user.role}). Essayez à nouveau ou contactez l'administrateur.", 'danger')
        return render_template('main/home.html')


@main_bp.route('/promote', methods=['GET', 'POST'])
@login_required
def promote():
    if current_user.role != 'data_viewer':
        abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'data_entry':
            return redirect(url_for('main.promote_data_entry'))
        elif action == 'district':
            return redirect(url_for('main.promote_district'))
    return render_template('data_viewer/promote.html')

@main_bp.route('/promote_data_entry', methods=['GET', 'POST'])
@login_required
def promote_data_entry():
    if current_user.role != 'data_viewer':
        abort(403)
    try:
        with current_app.app_context():
            regions = Location.query.filter_by(type='REG').all()
        if request.method == 'POST':
            region_id = request.form.get('region_id')
            data_entry_id = request.form.get('data_entry_id')
            with current_app.app_context():
                region = Location.query.get_or_404(region_id)
                data_entry = User.query.get_or_404(data_entry_id)
                team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
                if team_lead:
                    flash(f"Un Team Lead ({team_lead.name}) existe déjà pour la région {region.name}.", 'danger')
                    return redirect(url_for('main.promote_data_entry'))
                data_entry.role = 'team_lead'
                data_entry.location_id = region.id
                db.session.commit()
                flash(f"{data_entry.name} promu Team Lead pour {region.name}.", 'success')
            return redirect(url_for('main.dashboard'))
        return render_template('data_viewer/promote_data_entry.html', regions=regions)
    except SQLAlchemyError as e:
        current_app.logger.error(f"Erreur SQLAlchemy dans promote_data_entry : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors de la promotion.", 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/promote_district', methods=['GET', 'POST'])
@login_required
def promote_district():
    if current_user.role != 'data_viewer':
        abort(403)
    try:
        with current_app.app_context():
            regions = Location.query.filter_by(type='REG').all()
            districts = Location.query.filter_by(type='DIS').all()
        if request.method == 'POST':
            region_id = request.form.get('region_id')
            district_id = request.form.get('district_id')
            assigned_districts = request.form.getlist('assigned_districts')
            if len(assigned_districts) < 5:
                flash("Vous devez sélectionner au moins 5 districts.", 'danger')
                return redirect(url_for('main.promote_district'))
            with current_app.app_context():
                new_region = Location.query.get_or_404(district_id)
                new_region.type = 'REG'
                new_region.parent_id = None
                for dist_id in assigned_districts:
                    dist = Location.query.get(dist_id)
                    dist.parent_id = new_region.id
                db.session.commit()
                flash("Région créée et districts assignés.", 'success')
            return redirect(url_for('main.dashboard'))
        return render_template('data_viewer/promote_district.html', regions=regions, districts=districts)
    except SQLAlchemyError as e:
        current_app.logger.error(f"Erreur SQLAlchemy dans promote_district : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors de la promotion du district.", 'danger')
        return redirect(url_for('main.promote_district'))

@main_bp.route('/validate_requests', methods=['GET', 'POST'])
@login_required
def validate_requests():
    if current_user.role != 'data_viewer':
        abort(403)
    try:
        with current_app.app_context():
            pending_change_requests = ChangeRequest.query.options(
                joinedload(ChangeRequest.requester),
                joinedload(ChangeRequest.target_district),
                joinedload(ChangeRequest.target_region),
                joinedload(ChangeRequest.exchange_with)
            ).filter_by(status='pending_data_entry').all()
            pending_promotion_requests = PromotionRequest.query.options(
                joinedload(PromotionRequest.user),
                joinedload(PromotionRequest.requested_region)
            ).filter_by(status='pending').all()
        if request.method == 'POST':
            request_type = request.form.get('request_type')
            request_id = request.form.get('request_id')
            action = request.form.get('action')
            
            with current_app.app_context():
                if request_type == 'change':
                    req = ChangeRequest.query.get_or_404(request_id)
                    if action == 'validate':
                        user = req.requester
                        user.location_id = req.target_district_id
                        req.status = 'accepted'
                        req.responded_at = datetime.utcnow()
                        flash(f"Changement de localisation validé pour {user.name}.", 'success')
                    elif action == 'reject':
                        req.status = 'rejected'
                        req.responded_at = datetime.utcnow()
                        flash(f"Changement de localisation refusé pour {req.requester.name}.", 'info')
                elif request_type == 'promotion':
                    req = PromotionRequest.query.get_or_404(request_id)
                    if action == 'validate':
                        user = req.user
                        user.role = 'team_lead'
                        user.location_id = req.requested_region_id
                        req.status = 'accepted'
                        req.responded_at = datetime.utcnow()
                        flash(f"Promotion validée pour {user.name} en Team Lead.", 'success')
                    elif action == 'reject':
                        req.status = 'rejected'
                        req.responded_at = datetime.utcnow()
                        flash(f"Promotion refusée pour {req.user.name}.", 'info')
                db.session.commit()
            return redirect(url_for('main.validate_requests'))
        return render_template('data_viewer/validate_requests.html', 
                              pending_change_requests=pending_change_requests, 
                              pending_promotion_requests=pending_promotion_requests)
    except SQLAlchemyError as e:
        current_app.logger.error(f"Erreur SQLAlchemy dans validate_requests : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors de la validation des demandes.", 'danger')
        return redirect(url_for('main.dashboard'))