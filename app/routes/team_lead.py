from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, send_file
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
from sqlalchemy.orm import joinedload
from sqlalchemy import func

team_lead_bp = Blueprint('team_lead', __name__, template_folder='templates')

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

@team_lead_bp.route('/respond_request/<int:request_id>', methods=['GET', 'POST'])
@login_required
def respond_request(request_id):
    if current_user.role != 'team_lead':
        current_app.logger.error(f"Utilisateur {current_user.name} n'a pas le rôle team_lead")
        flash("Accès non autorisé.", 'danger')
        return redirect(url_for('main.index'))

    request_entry = ChangeRequest.query.get_or_404(request_id)
    if request_entry.status != 'pending_team_lead' or request_entry.new_region_id != current_user.location_id:
        current_app.logger.error(f"Demande {request_id} non valide pour team_lead {current_user.name}")
        flash("Demande non valide ou non autorisée.", 'danger')
        return redirect(url_for('team_lead.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        current_app.logger.debug(f"Action reçue : {action}")

        district_name = request_entry.new_district.name if request_entry.new_district else "Aucun district spécifié"

        if action == 'accept':
            request_entry.status = 'accepted'
            request_entry.team_lead_id = current_user.id
            request_entry.responded_at = datetime.utcnow()
            notification = Notification(
                user_id=request_entry.user_id,
                message=f"Votre demande de changement de localisation pour {district_name} a été acceptée par le Team Lead.",
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            flash("Demande acceptée avec succès.", 'success')
        elif action == 'reject':
            reason = request.form.get('reason')
            if not reason:
                flash("Veuillez fournir une raison pour le refus.", 'danger')
                return redirect(url_for('team_lead.dashboard'))
            request_entry.status = 'rejected'
            request_entry.team_lead_id = current_user.id
            request_entry.responded_at = datetime.utcnow()
            request_entry.reason = reason
            notification = Notification(
                user_id=request_entry.user_id,
                message=f"Votre demande de changement de localisation pour {district_name} a été rejetée par le Team Lead. Raison : {reason}.",
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            flash(f"Demande rejetée avec la raison : {reason}.", 'info')

        db.session.commit()
        current_app.logger.debug(f"Demande {request_id} mise à jour avec le statut : {request_entry.status}")
        return redirect(url_for('team_lead.dashboard'))

    return render_template('team_lead/respond_request.html', request=request_entry)

# Routes pour la gestion des membres
@team_lead_bp.route('/manage_members', methods=['GET', 'POST'])
@login_required
def manage_members():
    # Vérifier que l'utilisateur est un team_lead avec une région valide
    if current_user.role != 'team_lead' or not current_user.location or current_user.location.type != 'REG':
        flash("Accès non autorisé ou région non attribuée", 'danger')
        return redirect(url_for('main.dashboard'))

    form = TeamManagementForm()
    
    # Charger les membres (data_entry seulement)
    form.load_members(current_user.location_id)
    
    # Charger les districts de la région
    form.load_locations(current_user.location_id)

    if form.validate_on_submit():
        if form.submit_add.data:
            member = User.query.get(form.member.data)
            location = Location.query.get(form.location.data)
            
            # Validation supplémentaire
            if not member or not location:
                flash("Membre ou localisation invalide", "danger")
                return redirect(url_for('team_lead.manage_members'))
                
            if location.type != 'DIS' or location.parent_id != current_user.location_id:
                flash("Vous ne pouvez assigner qu'à des districts de votre région", "danger")
                return redirect(url_for('team_lead.manage_members'))

            if member.role != 'data_entry':
                flash("Vous ne pouvez assigner que des data_entry", "danger")
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

            # Vérifier que le membre est bien dans un district de la région
            if not member.location or member.location.parent_id != current_user.location_id:
                flash("Ce membre ne fait pas partie de vos districts", "danger")
            else:
                member.location_id = None
                db.session.commit()
                flash("Membre retiré avec succès", "success")
        
        return redirect(url_for('team_lead.manage_members'))

    # Récupérer les data_entry des districts de la région pour l'affichage
    districts = Location.query.filter_by(parent_id=current_user.location_id, type='DIS').all()
    district_ids = [d.id for d in districts]
    
    team_members = User.query.filter(
        User.role == 'data_entry',
        User.location_id.in_(district_ids) if district_ids else []
    ).all()

    # Calcul du TITE mensuel
    data_entry_ids = [m.id for m in team_members]
    one_month_ago = datetime.utcnow() - timedelta(days=30)
    total_tite = db.session.query(func.sum(DataEntry.tite))\
        .filter(DataEntry.user_id.in_(data_entry_ids))\
        .filter(DataEntry.date >= one_month_ago)\
        .scalar() or 0.0

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

@team_lead_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """Team lead dashboard with key metrics and pending requests"""
    # Authentication and authorization
    if current_user.role != 'team_lead':
        flash("Accès réservé aux Team Leads", 'danger')
        return redirect(url_for('main.index'))

    # Validate region assignment
    user_location = current_user.location
    if not user_location or user_location.type != 'REG':
        flash("Aucune région valide attribuée", 'danger')
        return render_template('team_lead/dashboard.html',
                            user_location=None,
                            metrics={},
                            pending_requests=[])

    try:
        # Get districts under this region
        districts = Location.query.filter_by(
            parent_id=user_location.id, 
            type='DIS'
        ).all()
        district_ids = [d.id for d in districts]

        # Get pending change requests
        pending_requests = ChangeRequest.query.filter(
            ChangeRequest.status == 'pending_team_lead',
            ChangeRequest.new_region_id == current_user.location_id
        ).options(
            joinedload(ChangeRequest.new_district),
            joinedload(ChangeRequest.new_region),
            joinedload(ChangeRequest.user)
        ).all()

        # Calculate team metrics
        one_month_ago = datetime.utcnow() - timedelta(days=30)
        metrics = {
            'districts_count': len(districts),
            'team_members': User.query.filter(
                User.role == 'data_entry',
                User.location_id.in_(district_ids)
            ).count(),
            'monthly_tite': db.session.query(func.sum(DataEntry.tite))
                .join(User, DataEntry.user_id == User.id)
                .filter(
                    User.role == 'data_entry',
                    User.location_id.in_(district_ids),
                    DataEntry.date >= one_month_ago
                ).scalar() or 0.0,
            'pending_requests_count': len(pending_requests)
        }

        return render_template(
            'team_lead/dashboard.html',
            user_location=user_location,
            metrics=metrics,
            pending_requests=pending_requests
        )

    except Exception as e:
        current_app.logger.error(f"Dashboard error: {str(e)}", exc_info=True)
        flash("Erreur de chargement du dashboard", 'danger')
        return render_template(
            'team_lead/dashboard.html',
            user_location=user_location,
            metrics={},
            pending_requests=[]
        )