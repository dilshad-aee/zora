"""
Category Routes - admin CRUD for playlist categories + public listing.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.auth.decorators import admin_required
from app.models import db, PlaylistCategory

bp = Blueprint('categories', __name__)


@bp.route('/categories', methods=['GET'])
@login_required
def list_categories():
    """List all categories (for filter dropdowns)."""
    categories = (
        PlaylistCategory.query
        .order_by(PlaylistCategory.sort_order.asc(), PlaylistCategory.name.asc())
        .all()
    )
    return jsonify([c.to_dict() for c in categories])


@bp.route('/admin/categories', methods=['POST'])
@admin_required
def create_category():
    """Create a new category."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()

    if not name:
        return jsonify({'error': 'Category name is required'}), 400
    if len(name) > 60:
        return jsonify({'error': 'Category name too long (max 60)'}), 400

    existing = PlaylistCategory.query.filter(
        db.func.lower(PlaylistCategory.name) == name.lower()
    ).first()
    if existing:
        return jsonify({'error': 'Category already exists'}), 409

    icon = str(data.get('icon', 'fa-music')).strip()[:30]
    color = str(data.get('color', '#6C5CE7')).strip()[:7]
    sort_order = int(data.get('sort_order', 0)) if str(data.get('sort_order', '')).isdigit() else 0

    category = PlaylistCategory(name=name, icon=icon, color=color, sort_order=sort_order)
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@bp.route('/admin/categories/<int:category_id>', methods=['PATCH'])
@admin_required
def update_category(category_id):
    """Update a category."""
    category = PlaylistCategory.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = str(data['name']).strip()
        if not name:
            return jsonify({'error': 'Category name is required'}), 400
        if len(name) > 60:
            return jsonify({'error': 'Category name too long (max 60)'}), 400
        dup = PlaylistCategory.query.filter(
            db.func.lower(PlaylistCategory.name) == name.lower(),
            PlaylistCategory.id != category_id,
        ).first()
        if dup:
            return jsonify({'error': 'Category name already exists'}), 409
        category.name = name

    if 'icon' in data:
        category.icon = str(data['icon']).strip()[:30]
    if 'color' in data:
        category.color = str(data['color']).strip()[:7]
    if 'sort_order' in data:
        try:
            category.sort_order = int(data['sort_order'])
        except (ValueError, TypeError):
            pass

    db.session.commit()
    return jsonify(category.to_dict())


@bp.route('/admin/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """Delete a category. Playlists in this category will have category_id set to NULL."""
    category = PlaylistCategory.query.get(category_id)
    if not category:
        return jsonify({'error': 'Category not found'}), 404

    db.session.delete(category)
    db.session.commit()
    return jsonify({'success': True})
