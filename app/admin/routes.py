"""
Admin Routes - User management, audit logs, and server status.
"""

import os
import sys
import time
import shutil
import platform
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import admin_required
from app.limiter import limiter
from app.models import db, User, AuditLog
from app.models.audit_log import log_action

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

bp = Blueprint('admin', __name__)

# ─── Server boot timestamp (for uptime calculation) ─────────────────────────
_SERVER_START_TIME = time.time()


def _safe(fn, default=None):
    """Run fn(), return default on any error."""
    try:
        return fn()
    except Exception:
        return default


def _get_cpu_info():
    """CPU usage and core count."""
    if not _HAS_PSUTIL:
        return None
    return {
        'percent': psutil.cpu_percent(interval=0.5),
        'cores_physical': psutil.cpu_count(logical=False),
        'cores_logical': psutil.cpu_count(logical=True),
        'frequency_mhz': _safe(lambda: round(psutil.cpu_freq().current)) if psutil.cpu_freq() else None,
    }


def _get_memory_info():
    """RAM usage."""
    if not _HAS_PSUTIL:
        return None
    mem = psutil.virtual_memory()
    return {
        'total_mb': round(mem.total / 1024 / 1024),
        'used_mb': round(mem.used / 1024 / 1024),
        'available_mb': round(mem.available / 1024 / 1024),
        'percent': mem.percent,
    }


def _get_disk_info():
    """Disk usage for the download directory partition."""
    from app.storage_paths import get_download_dir
    download_dir = str(get_download_dir())
    try:
        usage = shutil.disk_usage(download_dir)
        return {
            'total_gb': round(usage.total / 1024 / 1024 / 1024, 1),
            'used_gb': round(usage.used / 1024 / 1024 / 1024, 1),
            'free_gb': round(usage.free / 1024 / 1024 / 1024, 1),
            'percent': round(usage.used / usage.total * 100, 1) if usage.total else 0,
            'path': download_dir,
        }
    except Exception:
        return None


def _get_network_info():
    """Network I/O counters and active connections."""
    if not _HAS_PSUTIL:
        return None
    try:
        io = psutil.net_io_counters()
        connections = len(psutil.net_connections(kind='inet'))
    except (psutil.AccessDenied, PermissionError):
        connections = None
        io = psutil.net_io_counters()

    result = {
        'bytes_sent_mb': round(io.bytes_sent / 1024 / 1024, 1),
        'bytes_recv_mb': round(io.bytes_recv / 1024 / 1024, 1),
        'packets_sent': io.packets_sent,
        'packets_recv': io.packets_recv,
    }
    if connections is not None:
        result['active_connections'] = connections

    # Network interfaces + IPs
    try:
        addrs = psutil.net_if_addrs()
        interfaces = []
        for iface, addr_list in addrs.items():
            for addr in addr_list:
                if addr.family.name == 'AF_INET':
                    interfaces.append({'name': iface, 'ip': addr.address})
        result['interfaces'] = interfaces
    except Exception:
        pass

    return result


def _get_process_info():
    """Current Python process stats."""
    if not _HAS_PSUTIL:
        return {'pid': os.getpid()}
    try:
        proc = psutil.Process(os.getpid())
        mem_info = proc.memory_info()
        return {
            'pid': proc.pid,
            'memory_rss_mb': round(mem_info.rss / 1024 / 1024, 1),
            'threads': proc.num_threads(),
            'open_files': _safe(lambda: len(proc.open_files()), 0),
            'cpu_percent': proc.cpu_percent(interval=0),
        }
    except Exception:
        return {'pid': os.getpid()}


def _get_temperature():
    """CPU/device temperature (works on Termux/Linux, rare on macOS)."""
    if not _HAS_PSUTIL:
        return None
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Pick the first sensor with a current reading
        for name, entries in temps.items():
            for entry in entries:
                if entry.current and entry.current > 0:
                    return {
                        'sensor': name,
                        'label': entry.label or name,
                        'current_c': round(entry.current, 1),
                        'high_c': round(entry.high, 1) if entry.high else None,
                        'critical_c': round(entry.critical, 1) if entry.critical else None,
                    }
    except (AttributeError, Exception):
        pass
    return None


def _get_load_average():
    """System load average (1, 5, 15 min)."""
    try:
        load = os.getloadavg()
        return {
            'load_1m': round(load[0], 2),
            'load_5m': round(load[1], 2),
            'load_15m': round(load[2], 2),
        }
    except (OSError, AttributeError):
        return None


def _get_library_stats():
    """Library song count and total size."""
    from app.models import Download
    from app.storage_paths import get_download_dir

    total_songs = Download.query.count()
    total_users = User.query.count()

    # DB file size
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data.db')
    db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2) if os.path.exists(db_path) else 0

    # Calculate total music size on disk
    download_dir = get_download_dir()
    total_size_bytes = 0
    file_count = 0
    try:
        if download_dir.exists():
            for f in download_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    total_size_bytes += f.stat().st_size
                    file_count += 1
    except Exception:
        pass

    return {
        'total_songs': total_songs,
        'total_users': total_users,
        'files_on_disk': file_count,
        'total_size_mb': round(total_size_bytes / 1024 / 1024, 1),
        'db_size_mb': db_size_mb,
    }


def _get_queue_stats():
    """Active and queued download counts."""
    from app.services.queue_service import queue_service
    all_data = queue_service.get_all()
    active_count = len([d for d in all_data.get('active', []) if d.get('status') in ('downloading', 'pending', 'processing')])
    return {
        'queued': all_data.get('total', 0),
        'active': active_count,
    }


@bp.route('/server-status', methods=['GET'])
@admin_required
def server_status():
    """Comprehensive server status for admin dashboard."""
    uptime_sec = int(time.time() - _SERVER_START_TIME)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    return jsonify({
        'cpu': _get_cpu_info(),
        'memory': _get_memory_info(),
        'disk': _get_disk_info(),
        'network': _get_network_info(),
        'process': _get_process_info(),
        'temperature': _get_temperature(),
        'load_average': _get_load_average(),
        'library': _get_library_stats(),
        'queue': _get_queue_stats(),
        'uptime': {
            'seconds': uptime_sec,
            'formatted': f'{days}d {hours}h {minutes}m' if days else f'{hours}h {minutes}m',
        },
        'platform': {
            'python': platform.python_version(),
            'os': platform.system(),
            'arch': platform.machine(),
            'hostname': platform.node(),
        },
        'server_time': datetime.now().isoformat(),
        'has_psutil': _HAS_PSUTIL,
    })


@bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """List all users with pagination and search."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)
    search = request.args.get('search', '').strip()

    query = User.query

    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'users': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """Get single user detail."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


@bp.route('/users/<int:user_id>', methods=['PATCH'])
@admin_required
@limiter.limit("10 per minute")
def update_user(user_id):
    """Update user role or active status."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'role' in data:
        new_role = data['role']
        if new_role not in ('admin', 'user'):
            return jsonify({'error': 'Role must be admin or user'}), 400

        if user.role == 'admin' and new_role == 'user':
            admin_count = User.query.filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot demote the last admin'}), 409

        old_role = user.role
        user.role = new_role
        log_action('USER_ROLE_CHANGE', target_type='user', target_id=user_id,
                   metadata={'old_role': old_role, 'new_role': new_role})

    if 'is_active' in data:
        new_status = bool(data['is_active'])

        if not new_status and user.role == 'admin':
            admin_count = User.query.filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot deactivate the last admin'}), 409

        if user.id == current_user.id and not new_status:
            return jsonify({'error': 'Cannot deactivate yourself'}), 409

        old_status = user.is_active
        user.is_active = new_status
        action = 'USER_DEACTIVATE' if not new_status else 'USER_ACTIVATE'
        log_action(action, target_type='user', target_id=user_id,
                   metadata={'old_status': old_status, 'new_status': new_status})

    db.session.commit()
    return jsonify(user.to_dict())


@bp.route('/audit-logs', methods=['GET'])
@admin_required
def list_audit_logs():
    """List audit logs with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    per_page = min(per_page, 100)
    action_filter = request.args.get('action', '').strip()
    user_filter = request.args.get('user_id', type=int)

    query = AuditLog.query

    if action_filter:
        query = query.filter(AuditLog.action == action_filter)

    if user_filter:
        query = query.filter(AuditLog.actor_user_id == user_filter)

    query = query.order_by(AuditLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })
