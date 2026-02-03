
from app import create_app
from app.models import Download, db
import os

app = create_app()
with app.app_context():
    print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Check download count
    count = Download.query.count()
    print(f"Total downloads in DB: {count}")
    
    # Check sync logic (simulate request to history)
    print("Triggering history sync...")
    history = Download.get_history(limit=5)
    print(f"History after sync: {len(history)} items")
    for item in history:
        print(f" - {item.title} ({item.filename})")
        
    print(f"Final count in DB: {Download.query.count()}")
