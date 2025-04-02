# app/forms.py
from flask_wtf import FlaskForm
from wtforms import (
    DateField, StringField, PasswordField, SubmitField, SelectField,
    IntegerField, FloatField, TextAreaField, SelectMultipleField
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError, EqualTo, NumberRange
from app.models import User, Location
from datetime import datetime

class RegistrationForm(FlaskForm):
    """Formulaire d'inscription pour les nouveaux utilisateurs."""
    name = StringField('Nom complet', validators=[DataRequired(), Length(min=2, max=100)])
    matriculate = StringField('Matricule', validators=[DataRequired(), Length(min=5, max=20)])
    phone = StringField('Téléphone', validators=[DataRequired(), Length(min=8, max=15)])
    password = PasswordField('Mot de passe', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmer le mot de passe', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Rôle', choices=[
        ('data_entry', 'Saisie'),
        ('team_lead', 'Chef d\'équipe'),
        ('data_viewer', 'Visionneur')
    ], validators=[DataRequired()])
    location = SelectField('Localisation', coerce=int, validators=[DataRequired()])
    submit = SubmitField('S\'inscrire')

    def load_locations(self):
        """Charge dynamiquement les localisations disponibles."""
        if self.role.data == 'data_entry':
            self.location.choices = [(loc.id, loc.name) for loc in Location.query.filter_by(type='DIS').all()]
        else:
            self.location.choices = [(loc.id, loc.name) for loc in Location.query.all()]
        

    def validate_matriculate(self, field):
        """Vérifie que le matricule n'est pas déjà utilisé."""
        if User.query.filter_by(matriculate=field.data).first():
            raise ValidationError('Ce matricule est déjà utilisé.')

    def validate_phone(self, field):
        """Vérifie que le numéro de téléphone n'est pas déjà utilisé."""
        if User.query.filter_by(phone=field.data).first():
            raise ValidationError('Ce numéro de téléphone est déjà utilisé.')
        
    def validate_location(self, field):
        """Valide que la localisation est un district pour un data_entry."""
        location = Location.query.get(field.data)
        if self.role.data == 'data_entry' and location and location.type != 'DIS':
            raise ValidationError('Un utilisateur de type Data Entry doit être assigné à un district, pas à une région.')
        if self.role.data == 'team_lead' and location and location.type != 'REG':
            raise ValidationError('Un utilisateur de type Team Lead doit être assigné à une région, pas à un district.')

class LoginForm(FlaskForm):
    """Formulaire de connexion pour les utilisateurs."""
    matriculate = StringField('Matricule', validators=[DataRequired()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    submit = SubmitField('Se connecter')

class DataEntryForm(FlaskForm):
    """Formulaire pour la saisie des données par les utilisateurs 'data_entry'."""
    members = IntegerField('Nombre de membres', validators=[DataRequired(), NumberRange(min=0)])
    children = IntegerField('Nombre d\'enfants', validators=[DataRequired(), NumberRange(min=0)])
    men = IntegerField('Nombre d\'hommes', validators=[DataRequired(), NumberRange(min=0)])
    women = IntegerField('Nombre de femmes', validators=[DataRequired(), NumberRange(min=0)])
    tite = FloatField('Montant TITE (FCFA)', validators=[DataRequired(), NumberRange(min=0)])
    commentaire = TextAreaField('Commentaires', validators=[Optional(), Length(max=500)])
    location = SelectField('Localisation', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Valider les données')

    def load_locations(self, user_location_id=None):
        """Charge dynamiquement les localisations disponibles pour l'utilisateur."""
        if user_location_id:
            # Si l'utilisateur est lié à une localisation, limiter les choix à celle-ci
            location = Location.query.get(user_location_id)
            if location:
                self.location.choices = [(location.id, location.name)]
            else:
                self.location.choices = []
        else:
            # Sinon, charger toutes les localisations
            self.location.choices = [(loc.id, loc.name) for loc in Location.query.all()]

class LocationForm(FlaskForm):
    """Formulaire pour créer ou modifier une localisation (région ou district)."""
    code = StringField('Code', validators=[DataRequired(), Length(min=2, max=10)])
    name = StringField('Nom', validators=[DataRequired(), Length(min=2, max=100)])
    type = SelectField('Type', choices=[('REG', 'Région'), ('DIS', 'District')], validators=[DataRequired()])
    parent = SelectField('Région Parente', coerce=int, validators=[Optional()])
    submit = SubmitField('Ajouter')

    def load_locations(self):
        """Charge dynamiquement les régions parentes disponibles."""
        self.parent.choices = [(0, 'Aucune')] + [(loc.id, loc.name) for loc in Location.query.filter_by(type='REG').all()]

    def validate_parent(self, field):
        """Valide que le parent est une région si le type est un district."""
        if self.type.data == 'DIS' and field.data == 0:
            raise ValidationError('Un district doit avoir une région parente.')

class TeamManagementForm(FlaskForm):
    """Formulaire pour gérer les membres d'une équipe (ajout/suppression)."""
    member = SelectField('Membre', coerce=int, validators=[DataRequired()])
    location = SelectField('Localisation', coerce=int, validators=[DataRequired()])
    submit_add = SubmitField('Ajouter')
    submit_remove = SubmitField('Retirer')

    def load_locations(self, region_id=None):
        """Charge dynamiquement les localisations (districts) pour une région donnée."""
        if region_id:
            self.location.choices = [(loc.id, loc.name) for loc in Location.query.filter_by(parent_id=region_id, type='DIS').all()]
        else:
            self.location.choices = [(loc.id, loc.name) for loc in Location.query.filter_by(type='DIS').all()]

    def load_members(self, team_lead_id=None):
        """Charge dynamiquement tous les membres potentiels (data_entry)."""
        members = User.query.filter_by(role='data_entry').all()
        self.member.choices = [(user.id, user.name) for user in members]

class SelectRegionForm(FlaskForm):
    """Formulaire pour sélectionner une région (utilisé par team_lead pour changer de région)."""
    region = SelectField('Région', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Changer de région')

    def load_regions(self):
        """Charge dynamiquement les régions disponibles."""
        self.region.choices = [(r.id, r.name) for r in Location.query.filter_by(type='REG').all()]

class ChangeLocationForm(FlaskForm):
    """Formulaire pour demander un changement de localisation."""
    region = SelectField('Nouvelle Région', coerce=int, validators=[DataRequired()])
    district = SelectField('Nouveau District', coerce=int, validators=[DataRequired()])  # Remplacé Optional() par DataRequired()
    submit = SubmitField('Soumettre la Demande')

    def load_regions(self):
        """Charge dynamiquement les régions disponibles."""
        regions = Location.query.filter_by(type='REG').all()
        if not regions:
            raise ValidationError("Aucune région disponible. Veuillez contacter l'administrateur.")
        self.region.choices = [(r.id, r.name) for r in regions]

    def load_districts(self, region_id):
        """Charge dynamiquement les districts pour une région donnée."""
        districts = Location.query.filter_by(parent_id=region_id, type='DIS').all()
        if not districts:
            raise ValidationError("Aucun district disponible pour cette région.")
        self.district.choices = [(d.id, d.name) for d in districts]  # Supprimé l'option "Aucun"

    def validate_district(self, field):
        """Valide que le district sélectionné est valide."""
        if field.data:
            district = Location.query.get(field.data)
            if not district or district.type != 'DIS':
                raise ValidationError("Le district sélectionné est invalide.")

class PromotionRequestForm(FlaskForm):
    """Formulaire pour demander une promotion à team_lead."""
    region = SelectField('Région souhaitée', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Demander une Promotion')

    def load_regions(self):
        """Charge dynamiquement les régions disponibles."""
        self.region.choices = [(r.id, r.name) for r in Location.query.filter_by(type='REG').all()]

class MemberReportForm(FlaskForm):
    """Formulaire pour soumettre un rapport sur un membre de l'équipe."""
    member = SelectField('Membre', coerce=int, validators=[DataRequired()])
    performance = SelectField('Performance', choices=[
        ('excellent', 'Excellent'),
        ('good', 'Bon'),
        ('average', 'Moyen'),
        ('poor', 'À améliorer')
    ], validators=[DataRequired()])
    comments = TextAreaField('Commentaires', validators=[Optional(), Length(max=500)])
    date = DateField('Date du rapport', validators=[DataRequired()], default=datetime.now)
    submit = SubmitField('Enregistrer le rapport')

    def load_members(self, team_lead_id):
        """Charge dynamiquement les membres de la région du team_lead."""
        # Récupérer le team_lead pour obtenir sa région (location_id)
        team_lead = User.query.get(team_lead_id)
        # Charger les membres ayant role='member' et appartenant à la même région
        members = User.query.filter_by(role='member', location_id=team_lead.location_id).all()
        self.member.choices = [(m.id, m.name) for m in members]

class MonthlyReportForm(FlaskForm):
    """Formulaire pour soumettre un rapport mensuel."""
    month = SelectField('Mois', choices=[
        (1, 'Janvier'), (2, 'Février'), (3, 'Mars'),
        (4, 'Avril'), (5, 'Mai'), (6, 'Juin'),
        (7, 'Juillet'), (8, 'Août'), (9, 'Septembre'),
        (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre')
    ], coerce=int, validators=[DataRequired()], default=datetime.now().month)
    year = IntegerField('Année', validators=[DataRequired(), NumberRange(min=2000, max=2100)], default=datetime.now().year)
    achievements = TextAreaField('Réalisations', validators=[Optional(), Length(max=1000)])
    challenges = TextAreaField('Défis rencontrés', validators=[Optional(), Length(max=1000)])
    plans = TextAreaField('Plans pour le mois prochain', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Générer le rapport')

class DistrictTransferForm(FlaskForm):
    """Formulaire pour demander le transfert d'un district vers une autre région."""
    district = SelectField('District à transférer', coerce=int, validators=[DataRequired()])
    new_region = SelectField('Nouvelle région', coerce=int, validators=[DataRequired()])
    reason = TextAreaField('Raison du transfert', validators=[Optional(), Length(max=300)])
    submit = SubmitField('Demander le transfert')

    def load_districts(self, region_id):
        """Charge dynamiquement les districts pour une région donnée."""
        self.district.choices = [(d.id, d.name) for d in Location.query.filter_by(parent_id=region_id, type='DIS').all()]

    def load_regions(self):
        """Charge dynamiquement les régions disponibles."""
        self.new_region.choices = [(r.id, r.name) for r in Location.query.filter_by(type='REG').all()]