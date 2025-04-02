from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from app.models import Location, User
from app import db
from datetime import datetime

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Middleware pour restreindre l'accès aux rôles autorisés
def check_admin_role():
    if current_user.role not in ['data_viewer', 'team_lead']:
        abort(403)

# 1. Récupérer toutes les localisations (arborescence complète)
@api_bp.route('/locations', methods=['GET'])
@login_required
def get_all_locations():
    check_admin_role()
    def build_tree(locations, parent_id=None):
        tree = []
        for loc in locations.filter_by(parent_id=parent_id).all():
            node = {
                'id': loc.id,
                'code': loc.code,
                'name': loc.name,
                'type': loc.type,
                'team_lead': loc.team_lead.name if loc.team_lead else None,
                'children': build_tree(locations, loc.id)
            }
            tree.append(node)
        return tree
    
    locations = Location.query
    tree = build_tree(locations)
    return jsonify(tree)

# 2. Récupérer une localisation spécifique
@api_bp.route('/locations/<int:location_id>', methods=['GET'])
@login_required
def get_location(location_id):
    check_admin_role()
    location = Location.query.get_or_404(location_id)
    return jsonify({
        'id': location.id,
        'code': location.code,
        'name': location.name,
        'type': location.type,
        'parent_id': location.parent_id,
        'team_lead': location.team_lead.name if location.team_lead else None
    })

# 3. Créer une nouvelle localisation
@api_bp.route('/locations', methods=['POST'])
@login_required
def create_location():
    check_admin_role()
    data = request.form if request.form else request.get_json()
    if not data or 'code' not in data or 'name' not in data or 'type' not in data:
        return jsonify({'error': 'Code, name, and type are required'}), 400
    
    new_location = Location(
        code=data['code'],
        name=data['name'],
        type=data['type'],
        parent_id=data.get('parent_id'),
        created_at=datetime.utcnow()
    )
    try:
        db.session.add(new_location)
        db.session.commit()
        return jsonify({'id': new_location.id, 'message': 'Location created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 4. Mettre à jour une localisation
@api_bp.route('/locations/<int:location_id>', methods=['PUT'])
@login_required
def update_location(location_id):
    check_admin_role()
    location = Location.query.get_or_404(location_id)
    data = request.form if request.form else request.get_json()
    
    location.code = data.get('code', location.code)
    location.name = data.get('name', location.name)
    location.type = data.get('type', location.type)
    location.parent_id = data.get('parent', location.parent_id) or None
    
    try:
        db.session.commit()
        return jsonify({'message': 'Location updated successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 5. Supprimer une localisation
@api_bp.route('/locations/<int:location_id>', methods=['DELETE'])
@login_required
def delete_location(location_id):
    check_admin_role()
    location = Location.query.get_or_404(location_id)
    if location.children.count() > 0:
        return jsonify({'error': 'Cannot delete location with children'}), 400
    if User.query.filter_by(location_id=location_id).count() > 0:
        return jsonify({'error': 'Cannot delete location with assigned users'}), 400
    
    try:
        db.session.delete(location)
        db.session.commit()
        return jsonify({'message': 'Location deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 6. Liste des localisations pour formulaires (optionnel)
@api_bp.route('/locations/list', methods=['GET'])
@login_required
def get_locations_list():
    locations = Location.query.all()
    return jsonify([
        {'id': loc.id, 'code': loc.code, 'name': loc.name, 'type': loc.type}
        for loc in locations
    ])