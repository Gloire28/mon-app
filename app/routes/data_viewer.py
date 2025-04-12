# app/routes/data_viewer.py
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash, abort, send_file, current_app
from flask_login import login_required, current_user
from app.models import ChangeRequest, User, Location, DataEntry, TeamReport
from app.forms import LocationForm
from app import db
from datetime import datetime, timedelta
import io
import csv
from app.utils.performance import calculate_regional_performance

data_viewer_bp = Blueprint('data_viewer', __name__)

# Middleware pour vérifier le rôle Data Viewer
def check_data_viewer_role():
    if current_user.role != 'data_viewer':
        abort(403)


@data_viewer_bp.route('/create_region', methods=['GET', 'POST'])
@login_required
def create_region():
    check_data_viewer_role()
    
    form = LocationForm()
    form.type.data = 'REG'  # Pré-remplir le type comme Région
    form.parent.data = 0  # Pas de parent pour une région
    with current_app.app_context():
        form.load_locations()

    if form.validate_on_submit():
        with current_app.app_context():
            new_region = Location(
                code=form.code.data,
                name=form.name.data,
                type='REG',
                parent_id=None
            )
            db.session.add(new_region)
            db.session.commit()
            flash(f"Région {new_region.name} créée avec succès !", 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('data_viewer/create_region.html', form=form)

@data_viewer_bp.route('/team_details/<int:region_id>')
@login_required
def team_details(region_id):
    check_data_viewer_role()
    
    with current_app.app_context():
        region = Location.query.get_or_404(region)
        team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
        districts = Location.query.filter_by(parent_id=region.id, type='DIS').all()
        # Utilisation de la relation location
        data_entries = DataEntry.query.join(Location, DataEntry.location).filter(
            Location.id.in_([d.id for d in districts] + [region.id])
        ).all()
        team_reports = TeamReport.query.filter_by(team_lead_id=team_lead.id if team_lead else None).all()
    
    return render_template('data_viewer/team_details.html',
                         region=region,
                         team_lead=team_lead,
                         districts=districts,
                         data_entries=data_entries,
                         team_reports=team_reports)

@data_viewer_bp.route('/weekly-data/<int:region_id>')
@login_required
def weekly_data():
    check_data_viewer_role()
    
    with current_app.app_context():
        region = Location.query.get_or_404(region)
        start_date = datetime.now() - timedelta(days=30)
        # Utilisation de la relation location
        entries = DataEntry.query.join(Location, DataEntry.location).filter(
            Location.id.in_([loc.id for loc in region.children] + [region.id]),
            DataEntry.date >= start_date
        ).all()
    
    weekly_data = []
    for i in range(4):
        week_start = start_date + timedelta(days=7 * i)
        week_end = week_start + timedelta(days=7)
        week_entries = [e for e in entries if week_start <= e.date < week_end]
        weekly_data.append({
            'week': f"Semaine {i + 1}",
            'entries': len(week_entries),
            'user': ', '.join([e.user.name for e in week_entries]) if week_entries else 'Aucun'
        })
    
    return jsonify(weekly_data)

@data_viewer_bp.route('/export-weekly-data/<int:region_id>')
@login_required
def export_weekly_data(region_id):
    check_data_viewer_role()
    
    with current_app.app_context():
        region = Location.query.get_or_404(region)
        start_date = datetime.now() - timedelta(days=30)
        # Utilisation de la relation location
        entries = DataEntry.query.join(Location, DataEntry.location).filter(
            Location.id.in_([loc.id for loc in region.children] + [region.id]),
            DataEntry.date >= start_date
        ).all()
    
    weekly_data = []
    for i in range(4):
        week_start = start_date + timedelta(days=7 * i)
        week_end = week_start + timedelta(days=7)
        week_entries = [e for e in entries if week_start <= e.date < week_end]
        weekly_data.append({
            'week': f"Semaine {i + 1}",
            'entries': len(week_entries),
            'users': ', '.join([e.user.name for e in week_entries]) if week_entries else 'Aucun'
        })
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Semaine', 'Nombre d\'entrées', 'Utilisateurs'])
    for data in weekly_data:
        writer.writerow([data['week'], data['entries'], data['users']])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'weekly_data_region_{region}.csv'
    )

@data_viewer_bp.route('/export-monthly-data')
@login_required
def export_monthly_data():
    check_data_viewer_role()
    
    region_id = request.args.get('region_id', 'all')
    role = request.args.get('role', 'all')
    
    with current_app.app_context():
        regions = Location.query.filter_by(type='REG').all()
        start_date = datetime.now() - timedelta(days=365)
        
        if region_id == 'all':
            entries = DataEntry.query.filter(DataEntry.date >= start_date).all()
        else:
            region = Location.query.get_or_404(region_id)
            # Utilisation de la relation location
            entries = DataEntry.query.join(Location, DataEntry.location).filter(
                Location.id.in_([loc.id for loc in region.children] + [region.id]),
                DataEntry.date >= start_date
            ).all()
    
    if role != 'all':
        entries = [e for e in entries if e.user.role == role]
    
    monthly_data = {}
    for i in range(12):
        month_date = (datetime.now() - timedelta(days=30 * i)).replace(day=1)
        month_key = month_date.strftime('%b %Y')
        monthly_data[month_key] = 0
    
    for entry in entries:
        month_key = entry.date.strftime('%b %Y')
        if month_key in monthly_data:
            monthly_data[month_key] += entry.members
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Mois', 'Nombre de membres'])
    for month, members in monthly_data.items():
        writer.writerow([month, members])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'monthly_data_region_{region_id}_role_{role}.csv'
    )

@data_viewer_bp.route('/export-user-data')
@login_required
def export_user_data():
    check_data_viewer_role()
    
    with current_app.app_context():
        users = User.query.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Nom', 'Rôle', 'District', 'Région', 'Entrées', 'Rapport'])
        
        for user in users:
            district = user.location.name if user.location and user.location.type == 'DIS' else 'N/A'
            region = user.location.parent.name if user.location and user.location.parent else (user.location.name if user.location else 'N/A')
            total_entries = DataEntry.query.filter_by(user_id=user.id).count()
            report = DataEntry.query.filter_by(user_id=user.id).first()
            report_text = report.commentaire[:20] if report and report.commentaire else 'Aucun'
            writer.writerow([user.name, user.role, district, region, total_entries, report_text])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='user_data.csv'
    )

@data_viewer_bp.route('/regional_overview')
@login_required
def regional_overview():
    check_data_viewer_role()
    
    with current_app.app_context():
        regions = Location.query.filter_by(type='REG').all()
        regions_data = []
        
        for region in regions:
            team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
            performance = calculate_regional_performance(region.id)
            
            regions_data.append({
                'region': region,
                'team_lead': team_lead,
                'performance': performance
            })

        # Récupérer les données pour les graphiques
        monthly_data = {}
        for region in regions:
            monthly_data[region.id] = [0] * 12  # Initialiser avec 12 mois

        entries = DataEntry.query.filter(
            DataEntry.date >= datetime.now() - timedelta(days=365)
        ).all()

        for entry in entries:
            month = entry.date.month - 1  # 0-11
            if entry.location.parent_id in monthly_data:
                monthly_data[entry.location.parent_id][month] += entry.members
            elif entry.location_id in monthly_data:  # Si c'est une entrée directe pour une région
                monthly_data[entry.location_id][month] += entry.members

    return render_template('data_viewer/dashboard.html',
                         regions_data=regions_data,
                         monthly_data=monthly_data,
                         pending_change_requests=[],
                         pending_promotion_requests=[],
                         team_lead_reports=[],
                         data_entry_entries=[],
                         users_data=[])

@data_viewer_bp.route('/dashboard')
@login_required
def dashboard():
    check_data_viewer_role()
    
    # Récupération des données nécessaires pour le template dashboard.html
    regions = Location.query.filter_by(type='REG').all()
    regions_data = []
    
    for region in regions:
        team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
        performance = calculate_regional_performance(region.id)
        
        regions_data.append({
            'region': region,
            'team_lead': team_lead,
            'performance': performance
        })

    # Données pour les graphiques (comme dans votre template)
    monthly_data = {}
    for region in regions:
        monthly_data[region.id] = [0] * 12

    entries = DataEntry.query.filter(DataEntry.date >= datetime.now() - timedelta(days=365)).all()
    
    for entry in entries:
        month = entry.date.month - 1
        if entry.location.parent_id in monthly_data:
            monthly_data[entry.location.parent_id][month] += entry.members
        elif entry.location_id in monthly_data:
            monthly_data[entry.location_id][month] += entry.members

    # Rendu du template existant avec toutes les variables attendues
    return render_template('data_viewer/dashboard.html',
                         regions_data=regions_data,
                         monthly_data=monthly_data,
                         pending_change_requests=ChangeRequest.query.filter_by(status='pending').all(),
                         pending_promotion_requests=[],
                         team_lead_reports=TeamReport.query.order_by(TeamReport.created_at.desc()).limit(10).all(),
                         data_entry_entries=DataEntry.query.order_by(DataEntry.date.desc()).limit(10).all(),
                         users_data=User.query.all())