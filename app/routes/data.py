from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from wtforms import ValidationError
from app import db
from app.forms import DataEntryForm, ChangeLocationForm, PromotionRequestForm
from app.models import DataEntry, Location, Notification, User, ChangeRequest, PromotionRequest
from datetime import datetime
import logging
from sqlalchemy.orm import joinedload

# Création du blueprint pour les routes du rôle data_entry
data_bp = Blueprint('data', __name__, url_prefix='/data')

# Configuration du logging pour le débogage
logging.basicConfig(level=logging.DEBUG)

# Middleware pour vérifier que l'utilisateur a le rôle data_entry
def check_data_entry_role():
    if current_user.role != 'data_entry':
        abort(403)

@data_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """
    Affiche le tableau de bord pour un utilisateur data_entry.
    - Entrées récentes de l'utilisateur.
    - Demande de changement de localisation initiée par l'utilisateur.
    - Demandes de changement de localisation en attente de validation par l'utilisateur.
    - Demande de promotion en cours.
    """
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.dashboard")
    check_data_entry_role()
    
    # Compter les notifications non lues pour la messagerie
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, read=False).filter(
        Notification.message_id.isnot(None)  # Notifications liées à des messages
    ).count()
    
    with current_app.app_context():
        # Charger les entrées récentes de l'utilisateur
        entries = DataEntry.query.filter_by(user_id=current_user.id).order_by(DataEntry.date.desc()).limit(10).all()
        
        # Charger la demande de changement de localisation initiée par l'utilisateur
        initiated_change = ChangeRequest.query\
            .filter_by(requester_id=current_user.id)\
            .options(joinedload(ChangeRequest.requester), joinedload(ChangeRequest.target_district), joinedload(ChangeRequest.target_region))\
            .order_by(ChangeRequest.requested_at.desc())\
            .first()
        current_app.logger.debug(f"Demande initiée chargée : {initiated_change}")
        
        # Charger les demandes de changement de localisation en attente de validation par l'utilisateur
        # (par exemple, Gamal doit voir les demandes ciblant "Cotonou")
        pending_change = ChangeRequest.query\
            .filter(
                ChangeRequest.target_district_id == current_user.location_id,
                ChangeRequest.status == 'pending_data_entry'
            )\
            .options(joinedload(ChangeRequest.requester), joinedload(ChangeRequest.target_district), joinedload(ChangeRequest.target_region))\
            .first()
        current_app.logger.debug(f"Demande en attente de validation chargée : {pending_change}")
        
        # Charger la demande de promotion en cours de l'utilisateur
        pending_promotion = PromotionRequest.query\
            .options(joinedload(PromotionRequest.requested_region))\
            .filter_by(user_id=current_user.id, status='pending')\
            .first()
        current_app.logger.debug(f"Demande de promotion chargée : {pending_promotion}")

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
                          pending_change=pending_change or initiated_change,
                          change_request_status=change_request_status,
                          pending_promotion=pending_promotion,
                          unread_notifications=unread_notifications)

# Route : Faire une demande de changement de localisation
@data_bp.route('/change_location', methods=['GET', 'POST'])
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
                target_district_id = form.district.data
                target_district = Location.query.get_or_404(target_district_id)

                if target_district.type == 'REG':
                    flash("Erreur : Vous ne pouvez pas choisir une région comme district.", 'danger')
                    return redirect(url_for('data.change_location'))

                if target_district.id == current_user.location_id:
                    flash("Erreur : Vous êtes déjà assigné à ce district.", 'danger')
                    return redirect(url_for('data.change_location'))

                # Vérifier si un data_entry est assigné au district cible
                existing_data_entry = User.query.filter_by(location_id=target_district_id, role='data_entry').first()

                # Vérifier si un team_lead existe pour la région cible
                team_lead = User.query.filter_by(role='team_lead', location_id=target_district.parent_id).first()
                if not team_lead:
                    flash("Erreur : Aucun Team Lead trouvé pour valider cette demande.", 'danger')
                    return redirect(url_for('data.change_location'))

                # Vérifier si c'est un échange
                is_exchange = request.form.get('is_exchange') == 'on'
                exchange_with_user_id = None
                if is_exchange and existing_data_entry:
                    exchange_with_user_id = existing_data_entry.id

                # Créer une ChangeRequest
                request_entry = ChangeRequest(
                    requester_id=current_user.id,
                    target_district_id=target_district_id,
                    exchange_with_user_id=exchange_with_user_id,
                    status='pending_data_entry' if existing_data_entry else 'pending_team_lead',
                    requested_at=datetime.utcnow()
                )
                db.session.add(request_entry)

                # Ajouter une notification pour le destinataire
                recipient = existing_data_entry if existing_data_entry else team_lead
                if recipient:
                    message = (f"Nouvelle demande d'échange de localisation avec {current_user.name} pour le district {target_district.name}."
                              if is_exchange else
                              f"Nouvelle demande de changement de localisation de {current_user.name} pour le district {target_district.name}.")
                    notification = Notification(
                        user_id=recipient.id,
                        message=message,
                        created_at=datetime.utcnow()
                    )
                    db.session.add(notification)
                db.session.commit()

                flash(f"Demande de {'échange' if is_exchange else 'changement'} de localisation pour {target_district.name} envoyée avec succès.", 'success')
                return redirect(url_for('data.dashboard'))

            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Erreur dans le champ {field} : {error}", 'danger')
            return render_template('data_entry/change_location.html', form=form, step='district', region_id=region_id)

    return render_template('data_entry/change_location.html', form=form, step='region')

# Route : Répondre à une demande de changement de localisation
@data_bp.route('/respond_request/<int:request_id>', methods=['POST'])
@login_required
def respond_request(request_id):
    check_data_entry_role()

    try:
        request_entry = ChangeRequest.query.options(
            joinedload(ChangeRequest.requester),
            joinedload(ChangeRequest.target_district),
            joinedload(ChangeRequest.target_region),
            joinedload(ChangeRequest.exchange_with)
        ).get_or_404(request_id)
        
        if (request_entry.status != 'pending_data_entry' or 
            request_entry.target_district_id != current_user.location_id):
            abort(403)

        action = request.form.get('action')
        district_name = request_entry.target_district.name if request_entry.target_district else "Nouveau district"

        if action == 'accept':
            team_lead = User.query.filter_by(
                role='team_lead',
                location_id=request_entry.target_district.parent_id
            ).first()
            
            if not team_lead:
                flash("Aucun Team Lead trouvé pour cette région", 'danger')
                return redirect(url_for('data.dashboard'))

            request_entry.status = 'pending_team_lead'
            request_entry.data_entry_responded_at = datetime.utcnow()
            
            # Notifications
            message_prefix = "d'échange" if request_entry.exchange_with_user_id else "de transfert"
            notifications = [
                Notification(
                    user_id=team_lead.id,
                    message=f"Nouvelle demande {message_prefix} pour {district_name} de {request_entry.requester.name}",
                    created_at=datetime.utcnow()
                ),
                Notification(
                    user_id=request_entry.requester_id,
                    message=f"Votre demande {message_prefix} pour {district_name} est en attente du Team Lead",
                    created_at=datetime.utcnow()
                )
            ]
            db.session.add_all(notifications)
            flash("Demande transmise au Team Lead", 'success')

        elif action == 'reject':
            reason = request.form.get('reason', '').strip()
            if not reason or len(reason) < 10:
                flash("Veuillez fournir une raison d'au moins 10 caractères", 'danger')
                return redirect(url_for('data.dashboard'))
                
            request_entry.status = 'rejected'
            request_entry.reason = reason
            request_entry.data_entry_responded_at = datetime.utcnow()
            request_entry.completed_at = datetime.utcnow()
            
            db.session.add(Notification(
                user_id=request_entry.requester_id,
                message=f"Votre demande pour {district_name} a été rejetée. Raison: {reason}",
                created_at=datetime.utcnow()
            ))
            flash("Demande rejetée", 'info')

        db.session.commit()
        return redirect(url_for('data.dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur dans respond_request: {str(e)}", exc_info=True)
        flash("Erreur lors du traitement", 'danger')
        return redirect(url_for('data.dashboard'))

# Route : Faire une demande de promotion
@data_bp.route('/request-promotion', methods=['GET', 'POST'])
@login_required
def request_promotion():
    """
    Permet à un data_entry de faire une demande de promotion pour devenir Team Lead.
    """
    check_data_entry_role()

    form = PromotionRequestForm()
    with current_app.app_context():
        form.load_regions()

    if form.validate_on_submit():
        with current_app.app_context():
            # Vérifier si une demande de promotion est déjà en cours
            existing_request = PromotionRequest.query.filter_by(user_id=current_user.id, status='pending').first()
            if existing_request:
                flash("Vous avez déjà une demande de promotion en attente.", 'warning')
                return redirect(url_for('data.dashboard'))

            # Créer une nouvelle demande de promotion
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

# Route : Ajouter une nouvelle entrée de données
@data_bp.route('/new_entry', methods=['GET', 'POST'])
@login_required
def new_entry():
    """
    Permet à un data_entry d'ajouter une nouvelle entrée de données (DataEntry).
    """
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.new_entry")
    check_data_entry_role()
    
    form = DataEntryForm()
    with current_app.app_context():
        # Limiter les choix de localisation au district de l'utilisateur
        form.location.choices = [(loc.id, loc.name) for loc in Location.query.all()] if not current_user.location else [(current_user.location.id, current_user.location.name)]

    if form.validate_on_submit():
        current_app.logger.debug(f"Soumission du formulaire par {current_user.name}")
        # Vérifier la cohérence des données
        if form.members.data != (form.children.data + form.men.data + form.women.data):
            flash("Le nombre total de membres doit être égal à la somme des enfants, hommes et femmes.", 'danger')
            return render_template('data_entry/new_entry.html', form=form)
        
        with current_app.app_context():
            # Créer une nouvelle entrée
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

# Route : Modifier une entrée de données existante
@data_bp.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    """
    Permet à un data_entry de modifier une entrée de données existante (DataEntry).
    """
    current_app.logger.debug(f"Utilisateur {current_user.name} accède à data.edit_entry pour l'entrée {entry_id}")
    check_data_entry_role()
    
    with current_app.app_context():
        # Charger l'entrée à modifier
        entry = DataEntry.query.get_or_404(entry_id)
        if entry.user_id != current_user.id:
            abort(403)
    
    form = DataEntryForm(obj=entry)
    with current_app.app_context():
        form.location.choices = [(loc.id, loc.name) for loc in Location.query.all()] if not current_user.location else [(current_user.location.id, current_user.location.name)]
    
    if form.validate_on_submit():
        current_app.logger.debug(f"Soumission du formulaire d'édition par {current_user.name}")
        # Vérifier la cohérence des données
        if form.members.data != (form.children.data + form.men.data + form.women.data):
            flash("Le nombre total de membres doit être égal à la somme des enfants, hommes et femmes.", 'danger')
            return render_template('data_entry/edit_entry.html', form=form, entry=entry)
        
        with current_app.app_context():
            # Mettre à jour l'entrée
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