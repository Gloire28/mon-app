# app/routes/main.py
from flask import Blueprint, abort, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from app.models import DataEntry, Location, User, ChangeRequest, PromotionRequest, TeamReport
from app.forms import DataEntryForm
from app import db
from datetime import datetime, timedelta
from app.utils.performance import calculate_regional_performance
from sqlalchemy.orm import joinedload

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('main/home.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'data_entry':
        return redirect(url_for('data.dashboard'))

    elif current_user.role == 'team_lead':
        with current_app.app_context():
            # Validate region assignment
            if not current_user.location or current_user.location.type != 'REG':
                flash("Aucune région valide attribuée", 'danger')
                return render_template(
                    'team_lead/dashboard.html',
                    user_location=None,
                    metrics={'districts_count': 0, 'monthly_tite': 0.0, 'team_members': 0, 'pending_requests_count': 0},
                    pending_requests=[]
                )

            # Get districts under this region
            districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
            district_ids = [d.id for d in districts]

            # Calculate metrics
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
            
            # Get pending change requests
            pending_requests = ChangeRequest.query.options(
                joinedload(ChangeRequest.requester),
                joinedload(ChangeRequest.target_district),
                joinedload(ChangeRequest.target_region)
            ).filter(
                ChangeRequest.status == 'pending_team_lead',
                ChangeRequest.target_district_id.in_(district_ids)
            ).all()

            # Group metrics into a dictionary
            metrics = {
                'districts_count': districts_count,
                'team_members': team_members_count,
                'monthly_tite': monthly_tite,
                'pending_requests_count': len(pending_requests)
            }
            
            # Section "Mon District"
            form = DataEntryForm()
            form.load_locations(user_location_id=current_user.location_id)
            district_entries = DataEntry.query.filter_by(user_id=current_user.id).order_by(DataEntry.date.desc()).limit(10).all()
            district_entries_data = [
                {
                    'members': entry.members,
                    'tite': entry.tite if entry.tite is not None else 0,
                    'date': entry.date.strftime('%d/%m/%Y')
                }
                for entry in district_entries
            ]
        
        return render_template(
            'team_lead/dashboard.html',
            user_location=current_user.location,
            metrics=metrics,
            pending_requests=pending_requests,
            form=form,
            district_entries=district_entries,
            district_entries_data=district_entries_data
        )

    elif current_user.role == 'data_viewer':
        with current_app.app_context():
            regions = Location.query.filter_by(type='REG').all()
            regions_data = [
                {
                    'region': {'id': region.id, 'name': region.name},
                    'team_lead': {'name': team_lead.name} if (team_lead := User.query.filter_by(role='team_lead', location_id=region.id).first()) else None,
                    'performance': calculate_regional_performance(region.id)
                } for region in regions
            ]
            users_data = [
                {
                    'name': user.name,
                    'role': user.role,
                    'district': {'name': user.location.name} if user.location and user.location.type == 'DIS' else None,
                    'region': {'name': user.location.parent.name if user.location.parent else user.location.name} if user.location else None,
                    'total_entries': DataEntry.query.filter_by(user_id=user.id).count(),
                    'report': DataEntry.query.filter_by(user_id=user.id).first().commentaire if DataEntry.query.filter_by(user_id=user.id).first() else None
                } for user in User.query.options(joinedload(User.location)).all()
            ]
            monthly_data = {}
            start_date = datetime.now() - timedelta(days=365)
            for region in regions:
                entries = DataEntry.query.join(Location, DataEntry.location).filter(
                    Location.id.in_([loc.id for loc in region.children] + [region.id]),
                    DataEntry.date >= start_date
                ).all()
                monthly_totals = [0] * 12
                for entry in entries:
                    month_idx = entry.date.month - 1
                    monthly_totals[month_idx] += entry.members
                monthly_data[region.id] = monthly_totals
            
            team_lead_reports = TeamReport.query.options(
                joinedload(TeamReport.team_lead)
            ).join(User, TeamReport.team_lead_id == User.id).filter(
                User.role == 'team_lead'
            ).order_by(TeamReport.created_at.desc()).limit(10).all()
            
            data_entry_entries = DataEntry.query.options(
                joinedload(DataEntry.user),
                joinedload(DataEntry.location)
            ).join(User, DataEntry.user_id == User.id).filter(
                User.role == 'data_entry'
            ).order_by(DataEntry.date.desc()).limit(10).all()
            
            pending_change_requests = ChangeRequest.query.options(
                joinedload(ChangeRequest.requester),
                joinedload(ChangeRequest.target_district),
                joinedload(ChangeRequest.target_region)
            ).filter_by(status='pending_data_entry').all()
            pending_promotion_requests = PromotionRequest.query.options(
                joinedload(PromotionRequest.user),
                joinedload(PromotionRequest.requested_region)
            ).filter_by(status='pending').all()
        
        return render_template(
            'data_viewer/dashboard.html',
            regions_data=regions_data,
            users_data=users_data,
            monthly_data=monthly_data,
            pending_change_requests=pending_change_requests,
            pending_promotion_requests=pending_promotion_requests,
            team_lead_reports=team_lead_reports,
            data_entry_entries=data_entry_entries
        )
    
    return abort(403)

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
    with current_app.app_context():
        regions = Location.query.filter_by(type='REG').all()
    if request.method == 'POST':
        region_id = request.form.get('region_id')
        data_entry_id = request.form.get('data_entry_id')
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            data_entry = User.query.get_or_404(data_entry_id)
            team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
            data_entry.role = 'team_lead'
            data_entry.location_id = region.id
            db.session.commit()
            flash(f"{data_entry.name} promu Team Lead pour {region.name}.", 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('data_viewer/promote_data_entry.html', regions=regions)

@main_bp.route('/promote_district', methods=['GET', 'POST'])
@login_required
def promote_district():
    if current_user.role != 'data_viewer':
        abort(403)
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

@main_bp.route('/validate_requests', methods=['GET', 'POST'])
@login_required
def validate_requests():
    if current_user.role != 'data_viewer':
        abort(403)
    with current_app.app_context():
        pending_change_requests = ChangeRequest.query.filter_by(status='pending_data_entry').all()
        pending_promotion_requests = PromotionRequest.query.filter_by(status='pending').all()
    if request.method == 'POST':
        request_type = request.form.get('request_type')
        request_id = request.form.get('request_id')
        action = request.form.get('action')
        
        with current_app.app_context():
            if request_type == 'change':
                req = ChangeRequest.query.get_or_404(request_id)
                if action == 'validate':
                    user = req.requester  # Changé de req.user à req.requester
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