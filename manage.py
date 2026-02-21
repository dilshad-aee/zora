#!/usr/bin/env python3
"""
Zora CLI — Admin management commands.

Usage:
    python manage.py reset-admin

Reads ZORA_ADMIN_EMAIL and ZORA_ADMIN_PASSWORD from env vars (or .env file).
If the user exists, resets their password and ensures is_active=True.
If the user does not exist, creates a new admin account.
"""

import os
import sys


def _load_dotenv():
    """Load .env file if present (no dependency on python-dotenv)."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def reset_admin():
    """Reset or create the admin account from env vars."""
    _load_dotenv()

    email = os.getenv('ZORA_ADMIN_EMAIL')
    password = os.getenv('ZORA_ADMIN_PASSWORD')
    name = os.getenv('ZORA_ADMIN_NAME', 'Admin')

    if not email or not password:
        print("❌ ZORA_ADMIN_EMAIL and ZORA_ADMIN_PASSWORD must be set.")
        print("   Set them in your environment or .env file and retry.")
        sys.exit(1)

    email = email.strip().lower()

    if len(password) < 8:
        print("❌ ZORA_ADMIN_PASSWORD must be at least 8 characters.")
        sys.exit(1)

    from app import create_app
    app = create_app()

    with app.app_context():
        from app.models import db, User

        user = User.query.filter_by(email=email).first()

        if user:
            user.set_password(password)
            user.is_active = True
            user.role = 'admin'
            db.session.commit()
            print(f"✅ Password reset and account re-activated for {email}")
        else:
            user = User(
                name=name,
                email=email,
                role='admin',
                auth_provider='local',
                email_verified=True,
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print(f"✅ Admin account created for {email}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python manage.py <command>")
        print("Commands:")
        print("  reset-admin   Reset or create admin account from env vars")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'reset-admin':
        reset_admin()
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
