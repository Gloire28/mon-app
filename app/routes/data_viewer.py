from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash, abort, send_file, current_app, Response
from flask_login import login_required, current_user
from app.models import ChangeRequest, User, Location, DataEntry, TeamReport
from app.forms import LocationForm
from app import db
from datetime import datetime, timedelta
import io
import csv
from app.utils.performance import calculate_regional_performance
from sqlalchemy.orm import joinedload

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
    form.type.data = 'REG'
    form.parent.data = 0
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
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
            districts = Location.query.filter_by(parent_id=region.id, type='DIS').all()
            # Charger les data_entry pour chaque district
            district_data_entries = {}
            for district in districts:
                data_entry = User.query.filter_by(role='data_entry', location_id=district.id).first()
                district_data_entries[district.id] = data_entry
            team_reports = TeamReport.query.filter_by(team_lead_id=team_lead.id if team_lead else None).options(
                joinedload(TeamReport.team_lead),
                joinedload(TeamReport.member)
            ).all()
            # Calculer la performance de la région
            performance = calculate_regional_performance(region.id)
            # Charger les change_requests liés à la région (validés ou rejetés) avec les relations
            change_requests = ChangeRequest.query.join(Location, ChangeRequest.target_district_id == Location.id).filter(
                Location.parent_id == region.id,
                ChangeRequest.status.in_(['accepted', 'rejected'])
            ).options(
                joinedload(ChangeRequest.target_district),
                joinedload(ChangeRequest.requester)
            ).order_by(ChangeRequest.requested_at.desc()).limit(5).all()
        return render_template(
            'data_viewer/team_details.html',
            region=region,
            team_lead=team_lead,
            districts=districts,
            district_data_entries=district_data_entries,
            team_reports=team_reports,
            performance=performance,
            change_requests=change_requests
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans team_details : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors du chargement des détails.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/weekly-data/<int:region_id>')
@login_required
def weekly_data(region_id):
    check_data_viewer_role()
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            start_date = datetime.now() - timedelta(days=30)
            entries = DataEntry.query.join(Location).filter(
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
    except Exception as e:
        current_app.logger.error(f"Erreur dans weekly_data : {str(e)}", exc_info=True)
        return jsonify({'error': 'Erreur lors du chargement des données'}), 500

@data_viewer_bp.route('/export-weekly-data/<int:region_id>')
@login_required
def export_weekly_data(region_id):
    check_data_viewer_role()
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            start_date = datetime.now() - timedelta(days=30)
            entries = DataEntry.query.join(Location).filter(
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
        writer.writerow(['Semaine', "Nombre d'entrées", 'Utilisateurs'])
        for data in weekly_data:
            writer.writerow([data['week'], data['entries'], data['users']])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'weekly_data_region_{region.name}.csv'
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans export_weekly_data : {str(e)}", exc_info=True)
        flash("Erreur lors de l'exportation des données.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/export-monthly-data')
@login_required
def export_monthly_data():
    check_data_viewer_role()
    try:
        region_id = request.args.get('region_id', 'all')
        role = request.args.get('role', 'all')
        with current_app.app_context():
            regions = Location.query.filter_by(type='REG').all()
            start_date = datetime.now() - timedelta(days=365)
            if region_id == 'all':
                entries = DataEntry.query.filter(DataEntry.date >= start_date).all()
            else:
                region = Location.query.get_or_404(region_id)
                entries = DataEntry.query.join(Location).filter(
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
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'monthly_data_region_{region_id}_role_{role}.csv'
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans export_monthly_data : {str(e)}", exc_info=True)
        flash("Erreur lors de l'exportation des données.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/export-user-data')
@login_required
def export_user_data():
    check_data_viewer_role()
    try:
        with current_app.app_context():
            users = User.query.all()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Nom', 'Rôle', 'District', 'Région', 'Entrées', 'Rapport'])
            for user in users:
                district = user.location.name if user.location and user.location.type == 'DIS' else 'N/A'
                region = user.location.parent.name if user.location and user.location.parent else (user.location.name if user.location else 'N/A')
                total_entries = DataEntry.query.filter_by(user_id=user.id).count()
                report = DataEntry.query.filter_by(user_id=user.id).order_by(DataEntry.date.desc()).first()
                report_text = report.commentaire[:20] if report and report.commentaire else 'Aucun'
                writer.writerow([user.name, user.role, district, region, total_entries, report_text])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='user_data.csv'
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans export_user_data : {str(e)}", exc_info=True)
        flash("Erreur lors de l'exportation des données.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/region_entries/<int:region_id>', endpoint='region_entries_view')
@login_required
def region_entries(region_id):
    check_data_viewer_role()
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            if region.type != 'REG':
                flash("L'identifiant spécifié ne correspond pas à une région.", 'danger')
                return redirect(url_for('main.dashboard'))
            district_ids = [loc.id for loc in Location.query.filter_by(parent_id=region.id, type='DIS').all()]
            
            # Définir une plage de dates par défaut (30 derniers jours)
            interval_end = datetime.now()
            interval_start = interval_end - timedelta(days=30)
            
            page = request.args.get('page', 1, type=int)
            entries = DataEntry.query.options(
                joinedload(DataEntry.user),
                joinedload(DataEntry.location)
            ).filter(
                DataEntry.location_id.in_(district_ids + [region.id]),
                DataEntry.date >= interval_start,
                DataEntry.date <= interval_end
            ).order_by(DataEntry.date.desc()).paginate(page=page, per_page=15, error_out=False)
        
        return render_template(
            'data_viewer/region_entries.html',
            region=region,
            entries=entries,
            interval_start=interval_start,
            interval_end=interval_end
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans region_entries : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors du chargement des entrées.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/region_reports/<int:region_id>')
@login_required
def region_reports(region_id):
    check_data_viewer_role()
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            if region.type != 'REG':
                flash("L'identifiant spécifié ne correspond pas à une région.", 'danger')
                return redirect(url_for('main.dashboard'))
            team_lead = User.query.filter_by(role='team_lead', location_id=region.id).first()
            reports = TeamReport.query.options(
                joinedload(TeamReport.team_lead),
                joinedload(TeamReport.member)
            ).filter(
                TeamReport.team_lead_id == team_lead.id
            ).order_by(TeamReport.created_at.desc()).all() if team_lead else []
        return render_template(
            'data_viewer/region_reports.html',
            region=region,
            reports=reports,
            team_lead=team_lead
        )
    except Exception as e:
        current_app.logger.error(f"Erreur dans region_reports : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors du chargement des rapports.", 'danger')
        return redirect(url_for('main.dashboard'))

@data_viewer_bp.route('/export_region_entries/<int:region_id>', endpoint='export_region_entries_endpoint')
@login_required
def export_region_entries(region_id):
    check_data_viewer_role()
    try:
        with current_app.app_context():
            region = Location.query.get_or_404(region_id)
            if region.type != 'REG':
                flash("L'identifiant spécifié ne correspond pas à une région.", 'danger')
                return redirect(url_for('main.dashboard'))
            district_ids = [loc.id for loc in Location.query.filter_by(parent_id=region.id, type='DIS').all()]
            entries = DataEntry.query.options(
                joinedload(DataEntry.user),
                joinedload(DataEntry.location)
            ).filter(
                DataEntry.location_id.in_(district_ids + [region.id])
            ).order_by(DataEntry.date.desc()).all()
            if not entries:
                flash("Aucune entrée à exporter pour cette région.", 'warning')
                return redirect(url_for('main.dashboard'))
            
            # Préparer les données pour l'export CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Date', 'Membres', 'Femmes', 'Hommes', 'Enfants', 'Tithe', 'Commentaire', 'Utilisateur', 'Localisation'])
            for entry in entries:
                writer.writerow([
                    entry.date.strftime('%Y-%m-%d'),
                    entry.members,
                    entry.women,
                    entry.men,
                    entry.children,
                    entry.tite,
                    entry.commentaire,
                    entry.user.name if entry.user else 'N/A',
                    entry.location.name if entry.location else 'N/A'
                ])
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={"Content-Disposition": f"attachment;filename=region_entries_{region_id}.csv"}
            )
    except Exception as e:
        current_app.logger.error(f"Erreur dans export_region_entries : {str(e)}", exc_info=True)
        flash("Une erreur est survenue lors de l'exportation des données.", 'danger')
        return redirect(url_for('main.dashboard'))