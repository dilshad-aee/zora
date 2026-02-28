#!/bin/bash
echo "=== Termux Fast Setup ==="

echo "1. Stopping any stuck pip installs..."
pkill -f pip

echo "2. Installing pre-compiled cryptography and rust..."
pkg install -y python-cryptography rust

echo "3. Recreating environment with system packages linked..."
cd ~/zora
rm -rf venv || true
python3 -m venv --system-site-packages venv
source venv/bin/activate

echo "4. Installing Python dependencies..."
pip install -r requirements.txt

echo "5. Running Database Migration..."
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
    print('Migration complete!')
"

echo "6. Restarting Server in tmux..."
pkill -f 'gunicorn' 2>/dev/null
pkill -f 'run.py' 2>/dev/null
tmux kill-session -t zora 2>/dev/null

tmux new -ds zora "cd ~/zora && source venv/bin/activate && gunicorn -w 2 -b 0.0.0.0:5001 --timeout 120 'app:create_app()'"
echo "=== Server started! Access it via your Cloudflare tunnel. ==="
