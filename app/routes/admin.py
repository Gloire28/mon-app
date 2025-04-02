from flask import Blueprint, abort, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Location, User
from app.forms import LocationForm
from app.extensions import db

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/manage-locations', methods=['GET', 'POST'])
@login_required
def manage_locations():
    if current_user.role != 'data_viewer':
        abort(403)
    
    form = LocationForm()
    form.parent.choices = [(0, 'Aucun')] + [(loc.id, loc.name) for loc in Location.query.filter_by(type='REG')]
    
    if form.validate_on_submit():
        location = Location(
            code=form.code.data.upper(),
            name=form.name.data,
            type=form.type.data,
            parent_id=form.parent.data if form.parent.data != 0 else None
        )
        db.session.add(location)
        db.session.commit()
        flash('Localisation créée!', 'success')
        return redirect(url_for('admin.manage_locations'))
    
    locations = Location.query.all()
    return render_template('admin/manage_locations.html', form=form, locations=locations)