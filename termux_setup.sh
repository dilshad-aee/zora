#!/bin/bash
# Zora Setup script for Termux
echo "=== Installing Zora dependencies ==="
cd ~/zora
source venv/bin/activate

# Install pure python packages first, then the rust-heavy cryptography
pip install -r requirements.txt

echo "=== Running DB Migration ==="
python3 -c "
import sqlite3, os
from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.create_all()
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '').replace('sqlite://', '')
    if not os.path.exists(db_path): db_path = 'data.db'
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('PRAGMA table_info(playlists)')
    cols = {r[1] for r in c.fetchall()}
    
    print('Checking columns...')
    for col, defn in [
        ('description', 'TEXT NOT NULL DEFAULT \"\"'),
        ('visibility', 'VARCHAR(10) NOT NULL DEFAULT \"private\"'),
        ('category_id', 'INTEGER'),
        ('like_count', 'INTEGER NOT NULL DEFAULT 0')
    ]:
        if col not in cols:
            c.execute(f'ALTER TABLE playlists ADD COLUMN {col} {defn}')
            print('Added ' + col)
            
    conn.commit()
    conn.close()
    print('DB Ready')
"

echo "=== Stopping old server ==="
pkill -f 'gunicorn' 2>/dev/null
pkill -f 'run.py' 2>/dev/null

echo "=== Starting production server ==="
gunicorn -w 2 -b 0.0.0.0:5001 --timeout 120 'app:create_app()'
