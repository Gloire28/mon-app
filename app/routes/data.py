from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from wtforms import ValidationError
from app import db
from app.forms import DataEntryForm, ChangeLocationForm, PromotionRequestForm
from app.models import DataEntry, Location, Notification, User, ChangeRequest, PromotionRequest
from datetime import datetime
import logging
from sqlalchemy.orm import joinedload

data_bp = Blueprint('data', __name__, url_prefix='/data')

logging.basicConfig(level=logging.DEBUG)

# Middleware pour vérifier le rôle Data Entry
def check_data_entry_role():
    if current_user.role != 'data_entry':
        abort(403)

from sqlalchemy.orm import joinedload

@data_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.dashboard")
    check_data_entry_role()
    
    with current_app.app_context():
        # Charger les entrées récentes
        entries = DataEntry.query.filter_by(user_id=current_user.id).order_by(DataEntry.date.desc()).limit(10).all()
        
        # Charger la demande initiée par l'utilisateur
        initiated_change = ChangeRequest.query\
            .filter_by(user_id=current_user.id)\
            .options(joinedload(ChangeRequest.new_district), joinedload(ChangeRequest.new_region))\
            .order_by(ChangeRequest.requested_at.desc())\
            .first()
        current_app.logger.debug(f"Demande initiée chargée : {initiated_change}")
        
        # Charger la demande en attente de validation par l'utilisateur actuel (en tant que data_entry cible)
        pending_change = ChangeRequest.query\
            .filter_by(current_data_entry_id=current_user.id, status='pending_data_entry')\
            .options(joinedload(ChangeRequest.new_district), joinedload(ChangeRequest.new_region), joinedload(ChangeRequest.user))\
            .first()
        current_app.logger.debug(f"Demande en attente de validation chargée : {pending_change}")
        
        # Charger la demande de promotion avec sa relation
        pending_promotion = PromotionRequest.query\
            .options(joinedload(PromotionRequest.requested_region))\
            .filter_by(user_id=current_user.id, status='pending')\
            .first()
        current_app.logger.debug(f"pending_promotion chargé : {pending_promotion}")

        # Déterminer l'état des étapes pour la demande initiée
        change_request_status = type('Status', (), {
            'data_entry_validated': False,
            'team_lead_validated': False,
            'rejected': False,
            'rejected_by': None
        })()
        if initiated_change:
            if initiated_change.status in ['pending_team_lead', 'accepted']:
                change_request_status.data_entry_validated = True
            if initiated_change.status == 'accepted':
                change_request_status.team_lead_validated = True
            if initiated_change.status == 'rejected':
                change_request_status.rejected = True
                # Déterminer qui a rejeté la demande
                if initiated_change.status == 'rejected' and not change_request_status.data_entry_validated:
                    change_request_status.rejected_by = 'Data Entry'
                else:
                    change_request_status.rejected_by = 'Team Lead'

    # Préparer les données pour le graphique
    entries_data = [
        {
            'members': entry.members,
            'tite': entry.tite if entry.tite is not None else 0,
            'date': entry.date.strftime('%d/%m/%Y')
        }
        for entry in entries
    ]

    current_app.logger.debug("Rendu de data_entry/dashboard.html")
    return render_template('data_entry/dashboard.html', 
                          entries=entries,
                          entries_data=entries_data,
                          user_location=current_user.location,
                          parent_region=current_user.location.parent if current_user.location else None,
                          pending_change=pending_change or initiated_change,  # Afficher soit la demande initiée, soit celle en attente
                          change_request_status=change_request_status,
                          pending_promotion=pending_promotion)

@data_bp.route('/change-location', methods=['GET', 'POST'])
@login_required
def change_location():
    check_data_entry_role()

    form = ChangeLocationForm()
    with current_app.app_context():
        try:
            form.load_regions()
            current_app.logger.debug(f"Choices pour region : {form.region.choices}")
        except ValidationError as e:
            flash(str(e), 'danger')
            return render_template('data_entry/change_location.html', form=form, step='region')

    # Étape 1 : Soumission de la région
    if request.method == 'POST' and 'region' in request.form and 'district' not in request.form:
        region_id = request.form.get('region')
        if not region_id:
            current_app.logger.error("Champ region manquant dans la soumission de l'étape 1")
            flash("Erreur : Veuillez sélectionner une région.", 'danger')
            return render_template('data_entry/change_location.html', form=form, step='region')

        try:
            region_id = int(region_id)
        except (ValueError, TypeError):
            current_app.logger.error(f"region_id invalide : {region_id}")
            flash("Erreur : Région invalide.", 'danger')
            return render_template('data_entry/change_location.html', form=form, step='region')

        # Vérifier que region_id est dans les choices
        if region_id not in [choice[0] for choice in form.region.choices]:
            current_app.logger.error(f"region_id {region_id} non trouvé dans les choices : {form.region.choices}")
            flash("Erreur : Région sélectionnée invalide.", 'danger')
            return render_template('data_entry/change_location.html', form=form, step='region')

        with current_app.app_context():
            try:
                form.district.choices = [(loc.id, loc.name) for loc in Location.query.filter_by(parent_id=region_id, type='DIS').all()]
                current_app.logger.debug(f"Choices pour district : {form.district.choices}")
            except ValidationError as e:
                flash(str(e), 'danger')
                return render_template('data_entry/change_location.html', form=form, step='region')
        return render_template('data_entry/change_location.html', form=form, step='district', region_id=region_id)

    # Étape 2 : Soumission finale (après choix du district)
    if request.method == 'POST' and 'district' in request.form:
        with current_app.app_context():
            # Charger les choices pour region et district
            form.load_regions()
            region_id = request.form.get('region_id')
            if not region_id:
                current_app.logger.error("region_id manquant dans le formulaire de l'étape 2")
                flash("Erreur : Région non spécifiée.", 'danger')
                return render_template('data_entry/change_location.html', form=form, step='district', region_id=None)

            try:
                region_id = int(region_id)
            except (ValueError, TypeError):
                current_app.logger.error(f"region_id invalide dans l'étape 2 : {region_id}")
                flash("Erreur : Région invalide.", 'danger')
                return render_template('data_entry/change_location.html', form=form, step='district', region_id=None)

            districts = Location.query.filter_by(parent_id=region_id, type='DIS').all()
            form.district.choices = [(loc.id, loc.name) for loc in districts]
            if not form.district.choices:
                current_app.logger.error(f"Aucun district trouvé pour region_id : {region_id}")
                flash("Erreur : Aucun district disponible pour cette région.", 'danger')
                return render_template('data_entry/change_location.html', form=form, step='district', region_id=region_id)

            current_app.logger.debug(f"Données soumises dans l'étape 2 : {request.form}")
            if form.validate_on_submit():
                new_district_id = form.district.data
                new_district = Location.query.get_or_404(new_district_id)

                if new_district.type == 'REG':
                    flash("Erreur : Vous ne pouvez pas choisir une région comme district.", 'danger')
                    return redirect(url_for('data.change_location'))

                # Vérifier si un data_entry est assigné au district
                existing_data_entry = User.query.filter_by(location_id=new_district_id, role='data_entry').first()
                current_data_entry_id = existing_data_entry.id if existing_data_entry and existing_data_entry.id != current_user.id else None

                # Vérifier si un team_lead existe pour la région
                team_lead = User.query.filter_by(role='team_lead', location_id=new_district.parent_id).first()
                team_lead_id = team_lead.id if team_lead else None

                if not team_lead and not current_data_entry_id:
                    flash("Erreur : Aucun Team Lead ou Data Entry trouvé pour valider cette demande.", 'danger')
                    return redirect(url_for('data.change_location'))

                # Créer une ChangeRequest avec un statut initial
                team_lead = User.query.filter_by(
                    role='team_lead',
                    location_id=new_district.parent_id
                ).first()
                if not team_lead:
                    flash("Aucun Team Lead trouvé pour cette région", 'danger')
                    return redirect(url_for('data.change_location'))
                
                request_entry = ChangeRequest(
                    user_id=current_user.id,
                    new_region_id=new_district.parent_id,
                    new_district_id=new_district_id,
                    status='pending_data_entry' if current_data_entry_id else 'pending_team_lead',
                    requested_at=datetime.utcnow(),
                    current_data_entry_id=current_data_entry_id,
                    team_lead_id=team_lead.id
                )
                db.session.add(request_entry)
            

                # Ajouter une notification
                recipient = existing_data_entry if current_data_entry_id else team_lead
                if recipient:
                    notification = Notification(
                        user_id=recipient.id,
                        message=f"Nouvelle demande de changement de localisation de {current_user.name} pour le district {new_district.name}.",
                        created_at=datetime.utcnow()
                    )
                    db.session.add(notification)
                db.session.commit()

                flash(f"Demande de changement de localisation pour {new_district.name} envoyée avec succès.", 'success')
                return redirect(url_for('data.dashboard'))

            # Si la validation échoue, afficher les erreurs spécifiques
            current_app.logger.error(f"Erreurs de validation du formulaire dans l'étape 2 : {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Erreur dans le champ {field} : {error}", 'danger')
            return render_template('data_entry/change_location.html', form=form, step='district', region_id=region_id)

    return render_template('data_entry/change_location.html', form=form, step='region')

@data_bp.route('/respond_request/<int:request_id>', methods=['POST'])
@login_required
def respond_request(request_id):
    """Handle data entry's response to change location requests"""
    if current_user.role != 'data_entry':
        abort(403)

    try:
        # Get and validate request
        request_entry = ChangeRequest.query.options(
            joinedload(ChangeRequest.new_district),
            joinedload(ChangeRequest.new_region),
            joinedload(ChangeRequest.user)
        ).get_or_404(request_id)
        
        if (request_entry.status != 'pending_data_entry' or 
            request_entry.current_data_entry_id != current_user.id):
            abort(403)

        action = request.form.get('action')
        district_name = request_entry.new_district.name if request_entry.new_district else "Nouveau district"

        if action == 'accept':
            # Validate and process acceptance
            team_lead = User.query.filter_by(
                role='team_lead',
                location_id=request_entry.new_region_id
            ).first()
            
            if not team_lead:
                flash("Aucun Team Lead trouvé pour cette région", 'danger')
                return redirect(url_for('data.dashboard'))

            # Update request status
            request_entry.status = 'pending_team_lead'
            request_entry.team_lead_id = team_lead.id
            request_entry.responded_at = datetime.utcnow()
            
            # Create notifications
            notifications = [
                Notification(
                    user_id=team_lead.id,
                    message=f"Nouvelle demande de transfert pour {district_name} de {request_entry.user.name}",
                    created_at=datetime.utcnow()
                ),
                Notification(
                    user_id=request_entry.user_id,
                    message=f"Votre demande pour {district_name} est en attente du Team Lead",
                    created_at=datetime.utcnow()
                )
            ]
            db.session.add_all(notifications)
            flash("Demande transmise au Team Lead", 'success')

        elif action == 'reject':
            # Handle rejection
            reason = request.form.get('reason', 'Non spécifié').strip()
            if not reason:
                flash("Veuillez fournir une raison", 'danger')
                return redirect(url_for('data.dashboard'))
                
            request_entry.status = 'rejected'
            request_entry.reason = reason
            request_entry.responded_at = datetime.utcnow()
            
            db.session.add(Notification(
                user_id=request_entry.user_id,
                message=f"Votre demande pour {district_name} a été rejetée. Raison: {reason}",
                created_at=datetime.utcnow()
            ))
            flash("Demande rejetée", 'info')

        db.session.commit()
        return redirect(url_for('data.dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in respond_request: {str(e)}", exc_info=True)
        flash("Erreur lors du traitement", 'danger')
        return redirect(url_for('data.dashboard'))
    

@data_bp.route('/request-promotion', methods=['GET', 'POST'])
@login_required
def request_promotion():
    check_data_entry_role()

    form = PromotionRequestForm()
    with current_app.app_context():
        form.load_regions()

    if form.validate_on_submit():
        with current_app.app_context():
            existing_request = PromotionRequest.query.filter_by(user_id=current_user.id, status='pending').first()
            if existing_request:
                flash("Vous avez déjà une demande de promotion en attente.", 'warning')
                return redirect(url_for('data.dashboard'))

            promotion_request = PromotionRequest(
                user_id=current_user.id,
                requested_region_id=form.region.data,
                status='pending',
                requested_at=datetime.utcnow()
            )
            db.session.add(promotion_request)
            db.session.commit()
            flash("Demande de promotion envoyée au Data Viewer.", 'success')
        return redirect(url_for('data.dashboard'))

    return render_template('data_entry/request_promotion.html', form=form)

@data_bp.route('/new_entry', methods=['GET', 'POST'])
@login_required
def new_entry():
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.new_entry")
    check_data_entry_role()
    form = DataEntryForm()
    with current_app.app_context():
        form.location.choices = [(loc.id, loc.name) for loc in Location.query.all()] if not current_user.location else [(current_user.location.id, current_user.location.name)]

    if form.validate_on_submit():
        current_app.logger.debug(f"Soumission du formulaire par {current_user.name}")
        if form.members.data != (form.children.data + form.men.data + form.women.data):
            flash("Le nombre total de membres doit être égal à la somme des enfants, hommes et femmes.", 'danger')
            return render_template('data_entry/new_entry.html', form=form)
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
            try:
                db.session.add(entry)
                db.session.commit()
                flash('Données enregistrées avec succès !', 'success')
                current_app.logger.debug("Entrée enregistrée, redirection vers data.dashboard")
                return redirect(url_for('data.dashboard'))
            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de l’enregistrement : {str(e)}', 'danger')
                current_app.logger.error(f"Erreur lors de l’enregistrement : {str(e)}")

    current_app.logger.debug("Rendu de data_entry/new_entry.html")
    return render_template('data_entry/new_entry.html', form=form)

@data_bp.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.edit_entry pour l'entrée {entry_id}")
    check_data_entry_role()
    
    with current_app.app_context():
        entry = DataEntry.query.get_or_404(entry_id)
        if entry.user_id != current_user.id:
            abort(403)
    
    form = DataEntryForm(obj=entry)
    with current_app.app_context():
        form.location.choices = [(loc.id, loc.name) for loc in Location.query.all()] if not current_user.location else [(current_user.location.id, current_user.location.name)]
    
    if form.validate_on_submit():
        current_app.logger.debug(f"Soumission du formulaire d'édition par {current_user.name}")
        if form.members.data != (form.children.data + form.men.data + form.women.data):
            flash("Le nombre total de membres doit être égal à la somme des enfants, hommes et femmes.", 'danger')
            return render_template('data_entry/edit_entry.html', form=form, entry=entry)
        
        with current_app.app_context():
            entry.members = form.members.data
            entry.children = form.children.data
            entry.men = form.men.data
            entry.women = form.women.data
            entry.tite = form.tite.data
            entry.commentaire = form.commentaire.data
            entry.location_id = form.location.data
            
            try:
                db.session.commit()
                flash('Entrée mise à jour avec succès !', 'success')
                current_app.logger.debug("Entrée mise à jour, redirection vers data.dashboard")
                return redirect(url_for('data.dashboard'))
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Erreur lors de la mise à jour : {str(e)}")
                flash("Une erreur est survenue lors de la mise à jour. Veuillez réessayer.", 'danger')
    
    current_app.logger.debug("Rendu de data_entry/edit_entry.html")
    return render_template('data_entry/edit_entry.html', form=form, entry=entry)