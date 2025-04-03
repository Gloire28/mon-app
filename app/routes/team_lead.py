from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from app.models import Notification, User, Location, DataEntry, ChangeRequest, TeamReport
from app.forms import (
    DataEntryForm, DistrictTransferForm, TeamManagementForm, SelectRegionForm,
    LocationForm, MemberReportForm, MonthlyReportForm
)
from app import db
from datetime import datetime, timedelta
from app.utils.performance import calculate_regional_performance
from functools import wraps
from weasyprint import HTML
from io import BytesIO
from flask import send_file
from sqlalchemy.orm import joinedload
from sqlalchemy import func

team_lead_bp = Blueprint('team_lead', __name__)

# Décorateur pour vérifier le rôle Team Lead
def team_lead_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'team_lead':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Appliquer le décorateur à toutes les routes du blueprint
@team_lead_bp.before_request
@login_required
@team_lead_required
def before_request():
    pass

# Routes pour la gestion des membres
@team_lead_bp.route('/manage_members', methods=['GET', 'POST'])
@login_required
def manage_members():
    # Vérifier que l'utilisateur a une localisation
    if not current_user.location or current_user.location.type != 'REG':
        flash("Vous devez être affilié à une région pour gérer des membres.", 'danger')
        return redirect(url_for('main.dashboard'))

    form = TeamManagementForm()
    form.load_members()
    form.load_locations(region_id=current_user.location_id)

    if form.validate_on_submit():
        if form.submit_add.data:
            member = User.query.get(form.member.data)
            location = Location.query.get(form.location.data)
            if not member or not location:
                flash("Membre ou localisation invalide", "danger")
                return redirect(url_for('team_lead.manage_members'))

            if member.location_id == location.id:
                flash(f"{member.name} est déjà assigné à {location.name}", "warning")
            else:
                member.location_id = location.id
                db.session.commit()
                flash(f"{member.name} assigné à {location.name}", "success")

        elif form.submit_remove.data:
            member = User.query.get(form.member.data)
            if not member:
                flash("Membre introuvable", "danger")
                return redirect(url_for('team_lead.manage_members'))

            if member.location_id != current_user.location_id:
                flash("Ce membre ne fait pas partie de votre région", "danger")
            else:
                member.location_id = None
                db.session.commit()
                flash("Membre retiré avec succès", "success")
        return redirect(url_for('team_lead.manage_members'))

    # Charger les membres de l'équipe
    team_members = User.query.filter_by(role='member', location_id=current_user.location_id).all()

    # Calculer la somme des TITE des districts affiliés à la région
    # Étape 1 : Récupérer les districts de la région
    districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
    district_ids = [district.id for district in districts]

    # Étape 2 : Récupérer les utilisateurs (data_entry) assignés à ces districts
    data_entries = User.query.filter_by(role='data_entry').filter(User.location_id.in_(district_ids)).all()
    data_entry_ids = [user.id for user in data_entries]

    # Étape 3 : Calculer la somme des TITE des DataEntry pour ces utilisateurs
    # Optionnel : Filtrer par période (par exemple, dernier mois)
    one_month_ago = datetime.utcnow() - timedelta(days=30)
    total_tite = db.session.query(func.sum(DataEntry.tite))\
        .filter(DataEntry.user_id.in_(data_entry_ids))\
        .filter(DataEntry.date >= one_month_ago)\
        .scalar() or 0.0

    current_app.logger.debug(f"Somme totale des TITE pour la région {current_user.location.name} : {total_tite}")

    return render_template('team_lead/manage_members.html', 
                          form=form, 
                          team_members=team_members, 
                          total_tite=total_tite)

# Route pour gérer les districts
@team_lead_bp.route('/manage_districts', methods=['GET', 'POST'])
def manage_districts():
    if not current_user.location or current_user.location.type != 'REG':
        flash("Vous devez être affilié à une région pour gérer des districts.", 'danger')
        return redirect(url_for('main.dashboard'))

    districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
    return render_template('team_lead/manage_districts.html', districts=districts)

# Routes pour voir les membres
@team_lead_bp.route('/view_team_members')
def view_team_members():
    members = User.query.filter_by(role='member', location_id=current_user.location_id).all()
    member_data = []
    for member in members:
        entries = DataEntry.query.filter_by(user_id=member.id).order_by(DataEntry.date.desc()).limit(10).all()
        member_data.append({'member': member, 'entries': entries})
    return render_template('team_lead/view_team_members.html', member_data=member_data)

# Routes pour les districts
@team_lead_bp.route('/create_district', methods=['GET', 'POST'])
def create_district():
    if not current_user.location or current_user.location.type != 'REG':
        flash("Vous devez être affilié à une région pour créer un district.", 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = LocationForm()
    form.type.data = 'DIS'
    form.parent.data = current_user.location_id
    form.load_locations()

    if form.validate_on_submit():
        new_district = Location(
            code=form.code.data,
            name=form.name.data,
            type='DIS',
            parent_id=current_user.location_id
        )
        db.session.add(new_district)
        db.session.commit()
        flash(f"District {new_district.name} créé avec succès !", 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('team_lead/create_district.html', form=form)

@team_lead_bp.route('/transfer_district', methods=['GET', 'POST'])
def transfer_district():
    form = DistrictTransferForm()
    form.load_districts(current_user.location_id)
    form.load_regions()
    
    if form.validate_on_submit():
        district = Location.query.get(form.district.data)
        new_region = Location.query.get(form.new_region.data)
        if not district or not new_region:
            flash("District ou région invalide", "danger")
            return redirect(url_for('team_lead.transfer_district'))

        current_team_lead = User.query.filter_by(role='team_lead', location_id=district.parent_id).first()
        if not current_team_lead:
            flash("Aucun Team Lead trouvé pour ce district", "danger")
            return redirect(url_for('team_lead.transfer_district'))

        change_request = ChangeRequest(
            user_id=current_user.id,
            new_region_id=new_region.id,
            new_district_id=district.id,
            status='pending',
            requested_at=datetime.utcnow(),
            reason=form.reason.data
        )
        db.session.add(change_request)
        db.session.commit()
        flash(f"Demande de transfert du district {district.name} envoyée à {current_team_lead.name}.", 'info')
        return redirect(url_for('main.dashboard'))
    
    return render_template('team_lead/transfer_district.html', form=form)

# Routes pour les rapports
@team_lead_bp.route('/report/member', methods=['GET', 'POST'])
def member_report():
    form = MemberReportForm()
    form.load_members(team_lead_id=current_user.id)
    
    if form.validate_on_submit():
        report = TeamReport(
            team_lead_id=current_user.id,
            member_id=form.member.data,
            performance=form.performance.data,
            comments=form.comments.data,
            created_at=form.date.data
        )
        db.session.add(report)
        db.session.commit()
        flash('Rapport membre enregistré avec succès', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('team_lead/team_reports/member_report.html', form=form)

@team_lead_bp.route('/report/monthly', methods=['GET', 'POST'])
def monthly_report():
    form = MonthlyReportForm()
    form.year.data = datetime.now().year
    
    if form.validate_on_submit():
        report = TeamReport(
            team_lead_id=current_user.id,
            member_id=None,
            performance=None,
            comments=f"Réalisations: {form.achievements.data}\nDéfis: {form.challenges.data}\nPlans: {form.plans.data}",
            created_at=datetime(form.year.data, form.month.data, 1),
            month=form.month.data,
            year=form.year.data
        )
        db.session.add(report)
        db.session.commit()
        flash('Rapport mensuel enregistré avec succès', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('team_lead/team_reports/monthly_report.html', form=form)

# Autres routes
@team_lead_bp.route('/change_region', methods=['GET', 'POST'])
def change_region():
    form = SelectRegionForm()
    form.load_regions()

    if form.validate_on_submit():
        new_region = Location.query.get(form.region.data)
        if not new_region:
            flash("Région invalide", "danger")
            return redirect(url_for('team_lead.change_region'))

        existing_team_lead = User.query.filter_by(role='team_lead', location_id=new_region.id).first()
        if existing_team_lead and existing_team_lead.id != current_user.id:
            change_request = ChangeRequest(
                user_id=current_user.id,
                new_region_id=new_region.id,
                new_district_id=None,
                status='pending',
                requested_at=datetime.utcnow()
            )
            db.session.add(change_request)
            db.session.commit()
            flash(f"Demande de changement de région envoyée à {existing_team_lead.name}.", 'info')
        else:
            current_user.location_id = new_region.id
            db.session.commit()
            flash(f"Région changée à {new_region.name}.", 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('team_lead/change_region.html', form=form)

@team_lead_bp.route('/respond_request/<int:request_id>', methods=['POST'])
def respond_request(request_id):
    request_entry = ChangeRequest.query.get_or_404(request_id)
    if request_entry.status != 'pending_team_lead' or current_user.location_id != request_entry.new_region_id:
        abort(403)

    action = request.form.get('action')

    if action == 'accept':
        request_entry.status = 'accepted'
        request_entry.responded_at = datetime.utcnow()
        # Mettre à jour la localisation de l'utilisateur
        user = request_entry.user
        if user and request_entry.new_district:
            user.location_id = request_entry.new_district_id
            # Notifier le demandeur
            notification = Notification(
                user_id=user.id,
                message=f"Votre demande de changement de localisation pour {request_entry.new_district.name} a été acceptée par le Team Lead.",
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            flash("Demande acceptée. La localisation de l'utilisateur a été mise à jour.", 'success')
        else:
            flash("Erreur : Utilisateur ou district introuvable.", 'danger')
    elif action == 'reject':
        reason = request.form.get('reason')
        request_entry.status = 'rejected'
        request_entry.reason = reason
        request_entry.responded_at = datetime.utcnow()
        # Notifier le demandeur
        if request_entry.user:
            notification = Notification(
                user_id=request_entry.user.id,
                message=f"Votre demande de changement de localisation pour {request_entry.new_district.name} a été rejetée par le Team Lead. Raison : {reason}.",
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            flash(f"Demande rejetée avec la raison : {reason}.", 'info')
        else:
            flash("Erreur : Utilisateur introuvable.", 'danger')
    db.session.commit()
    return redirect(url_for('main.dashboard'))

@team_lead_bp.route('/performance_report')
def performance_report():
    performance = calculate_regional_performance(current_user.location_id)
    
    start_date = datetime.now() - timedelta(days=180)
    entries = DataEntry.query.filter(
        DataEntry.location.has(parent_id=current_user.location_id),
        DataEntry.date >= start_date
    ).all()
    
    monthly_data = {}
    for i in range(6):
        month_date = (datetime.now() - timedelta(days=30 * i)).replace(day=1)
        month_key = month_date.strftime('%b %Y')
        monthly_data[month_key] = {'members': 0, 'tite': 0.0}
    
    for entry in entries:
        month_key = entry.date.strftime('%b %Y')
        if month_key in monthly_data:
            monthly_data[month_key]['members'] += entry.members
            monthly_data[month_key]['tite'] += float(entry.tite or 0)
    
    districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
    district_performance = []
    for district in districts:
        district_entries = DataEntry.query.filter(DataEntry.location == district).all()
        total_members = sum(e.members for e in district_entries)
        total_tite = sum(float(e.tite or 0) for e in district_entries)
        district_performance.append({
            'name': district.name,
            'members': total_members,
            'tite': total_tite
        })
    
    top_members = sorted(district_performance, key=lambda x: x['members'], reverse=True)[:3]
    bottom_members = sorted(district_performance, key=lambda x: x['members'])[:3]
    top_tite = sorted(district_performance, key=lambda x: x['tite'], reverse=True)[:3]
    bottom_tite = sorted(district_performance, key=lambda x: x['tite'])[:3]
    
    performance_data = {
        'labels': list(monthly_data.keys()),
        'members': [data['members'] for data in monthly_data.values()],
        'tite': [data['tite'] for data in monthly_data.values()]
    }
    
    return render_template('team_lead/performance_report.html', 
                         performance=performance,
                         performance_data=performance_data,
                         top_members=top_members,
                         bottom_members=bottom_members,
                         top_tite=top_tite,
                         bottom_tite=bottom_tite)

@team_lead_bp.route('/export_monthly_report')
def export_monthly_report():
    report = TeamReport.query.filter_by(
        team_lead_id=current_user.id,
        member_id=None
    ).order_by(TeamReport.created_at.desc()).first()

    if not report:
        flash("Aucun rapport mensuel trouvé", "danger")
        return redirect(url_for('team_lead.monthly_report'))
    comments_processed = report.comments.replace('\n', '<br>')

    html_content = f"""
    <h1>Rapport Mensuel - {current_user.location.name}</h1>
    <p><strong>Date:</strong> {report.created_at.strftime('%B %Y')}</p>
    <p><strong>Commentaires:</strong></p>
    <p>{comments_processed}</p>
    """
    pdf_file = BytesIO()
    HTML(string=html_content).write_pdf(pdf_file)
    pdf_file.seek(0)

    return send_file(
        pdf_file,
        as_attachment=True,
        download_name=f"rapport_mensuel_{report.created_at.strftime('%Y%m')}.pdf",
        mimetype='application/pdf'
    )

@team_lead_bp.route('/new_entry', methods=['GET', 'POST'])
@login_required
def new_entry():
    if current_user.role != 'team_lead':
        abort(403)
    form = DataEntryForm()
    form.load_locations(user_location_id=current_user.location_id)
    if form.validate_on_submit():
        if form.members.data != (form.children.data + form.men.data + form.women.data):
            flash("Le nombre total de membres doit être égal à la somme des enfants, hommes et femmes.", 'danger')
            return render_template('team_lead/new_entry.html', form=form)
        with current_app.app_context():
            entry = DataEntry(
                date=datetime.utcnow(),
                members=form.members.data,
                children=form.children.data,
                men=form.men.data,
                women=form.women.data,
                tite=form.tite.data,
                commentaire=form.commentaire.data,
                user_id=current_user.id,
                location_id=form.location.data
            )
            db.session.add(entry)
            db.session.commit()
            flash('Données enregistrées avec succès !', 'success')
            return redirect(url_for('main.dashboard'))
    return render_template('team_lead/new_entry.html', form=form)