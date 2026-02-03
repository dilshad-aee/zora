#!/bin/bash

# ============================================
# ZORA DEBUG SCRIPT
# ============================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ZORA_DIR="$HOME/zora"

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}          ZORA DEBUG REPORT${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo ""

cd "$ZORA_DIR"
source venv/bin/activate 2>/dev/null

# ============================================
# 1. FILES CHECK
# ============================================
echo -e "${GREEN}[1] FILES${NC}"
echo "Main files:"
[ -f "run.py" ] && echo "  ✓ run.py" || echo "  ✗ run.py"
[ -f "main.py" ] && echo "  ✓ main.py" || echo "  ✗ main.py"
[ -f "server.py" ] && echo "  ✓ server.py" || echo "  ✗ server.py"
[ -f "data.db" ] && echo "  ✓ data.db" || echo "  ✗ data.db"

echo ""
echo "App folder:"
ls -la app/ 2>/dev/null || echo "  No app folder"

echo ""
echo "Config folder:"
ls -la config/ 2>/dev/null || echo "  No config folder"
echo ""

# ============================================
# 2. DOWNLOADS
# ============================================
echo -e "${GREEN}[2] DOWNLOADS FOLDER${NC}"
if [ -d "downloads" ]; then
    FILE_COUNT=$(ls -1 downloads/ 2>/dev/null | wc -l | tr -d ' ')
    echo "Files in downloads: $FILE_COUNT"
    ls -la downloads/ 2>/dev/null | head -5
else
    echo "No downloads folder"
fi
echo ""

# ============================================
# 3. DATABASE CHECK
# ============================================
echo -e "${GREEN}[3] DATABASE${NC}"

python3 << 'PYEOF'
try:
    from app import create_app
    from app.models.download import Download
    
    app = create_app()
    with app.app_context():
        count = Download.query.count()
        print(f"Total records: {count}")
        
        if count > 0:
            latest = Download.query.order_by(Download.id.desc()).first()
            print(f"Latest title: {latest.title}")
            print(f"Video ID: {latest.video_id}")
            print(f"Thumbnail: {latest.thumbnail if latest.thumbnail else 'NONE'}")
            print(f"Filename: {latest.filename}")
        else:
            print("NO RECORDS IN DATABASE!")
except Exception as e:
    print(f"Error: {e}")
PYEOF
echo ""

# ============================================
# 4. IMPORT TEST
# ============================================
echo -e "${GREEN}[4] IMPORTS${NC}"

python3 << 'PYEOF'
errors = []

try:
    from app import create_app
    print("✓ app.create_app")
except Exception as e:
    print(f"✗ create_app: {e}")
    errors.append(str(e))

try:
    from app.routes import bp
    print("✓ app.routes")
except Exception as e:
    print(f"✗ routes: {e}")
    errors.append(str(e))

try:
    from app.downloader import YTMusicDownloader
    print("✓ downloader")
except Exception as e:
    print(f"✗ downloader: {e}")
    errors.append(str(e))

try:
    from app.models.download import Download
    print("✓ Download model")
except Exception as e:
    print(f"✗ Download: {e}")
    errors.append(str(e))

try:
    from app.services.youtube import YouTubeService
    print("✓ YouTubeService")
except Exception as e:
    print(f"✗ YouTubeService: {e}")
    errors.append(str(e))

if errors:
    print(f"\n{len(errors)} ERRORS!")
PYEOF
echo ""

# ============================================
# 5. YOUTUBE TEST
# ============================================
echo -e "${GREEN}[5] YOUTUBE SERVICE${NC}"

python3 << 'PYEOF'
try:
    from app.services.youtube import YouTubeService
    
    info = YouTubeService.get_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    print(f"Title: {info.get('title')}")
    print(f"ID: {info.get('id')}")
    thumb = info.get('thumbnail')
    print(f"Thumbnail: {thumb[:60] if thumb else 'NONE'}...")
except Exception as e:
    print(f"Error: {e}")
PYEOF
echo ""

# ============================================
# 6. ROUTES CHECK
# ============================================
echo -e "${GREEN}[6] ROUTES.PY CHECK${NC}"

ROUTES_FILE="app/routes.py"
if [ -f "$ROUTES_FILE" ]; then
    echo "Checking routes.py..."
    
    grep -q "def save_track" "$ROUTES_FILE" && echo "  ✓ save_track found" || echo "  ✗ save_track NOT FOUND"
    grep -q "Download.add" "$ROUTES_FILE" && echo "  ✓ Download.add found" || echo "  ✗ Download.add NOT FOUND"
    grep -q "app.app_context" "$ROUTES_FILE" && echo "  ✓ app_context found" || echo "  ✗ app_context NOT FOUND"
    grep -q "thumbnail" "$ROUTES_FILE" && echo "  ✓ thumbnail found" || echo "  ✗ thumbnail NOT FOUND"
else
    echo "routes.py not found!"
fi
echo ""

# ============================================
# 7. SHOW SAVE_TRACK
# ============================================
echo -e "${GREEN}[7] SAVE_TRACK FUNCTION${NC}"
grep -n -A 25 "def save_track" app/routes.py 2>/dev/null | head -30
echo ""

# ============================================
# 8. WHERE SAVE_TRACK CALLED
# ============================================
echo -e "${GREEN}[8] WHERE SAVE_TRACK IS CALLED${NC}"
grep -n "save_track" app/routes.py 2>/dev/null
echo ""

# ============================================
# 9. FULL DOWNLOAD TEST
# ============================================
echo -e "${GREEN}[9] FULL DOWNLOAD TEST${NC}"
echo "Testing actual download and save..."

python3 << 'PYEOF'
import os

try:
    from app import create_app
    from app.downloader import YTMusicDownloader
    from app.models.download import Download
    from config import config
    
    print("1. Initializing downloader...")
    downloader = YTMusicDownloader(
        output_dir=str(config.DOWNLOAD_DIR),
        audio_format='mp3',
        quality='128'
    )
    
    print("2. Downloading short test video...")
    # Very short video for testing
    result = downloader.download_single("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    
    print(f"\n3. Result:")
    print(f"   Success: {result.get('success')}")
    print(f"   Title: {result.get('title')}")
    print(f"   ID: {result.get('id')}")
    print(f"   Thumbnail: {result.get('thumbnail', 'NONE')[:50] if result.get('thumbnail') else 'NONE'}")
    print(f"   Filename: {result.get('filename')}")
    
    if result.get('success'):
        print("\n4. Saving to database...")
        app = create_app()
        with app.app_context():
            existing = Download.query.filter_by(video_id=result.get('id')).first()
            if existing:
                print(f"   Already exists: {existing.title}")
            else:
                Download.add(
                    video_id=result.get('id'),
                    title=result.get('title', 'Unknown'),
                    artist=result.get('uploader', 'Unknown'),
                    filename=os.path.basename(result.get('filename', '')),
                    thumbnail=result.get('thumbnail', ''),
                    duration=result.get('duration', 0)
                )
                print("   ✓ SAVED TO DATABASE!")
            
            # Verify
            record = Download.query.filter_by(video_id=result.get('id')).first()
            if record:
                print(f"\n5. Verification:")
                print(f"   DB ID: {record.id}")
                print(f"   DB Title: {record.title}")
                print(f"   DB Thumbnail: {record.thumbnail if record.thumbnail else 'NONE'}")
            else:
                print("\n   ✗ RECORD NOT SAVED!")
    
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
PYEOF
echo ""

# ============================================
# SUMMARY
# ============================================
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}                    DONE${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"