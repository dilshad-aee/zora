#!/data/data/com.termux/files/usr/bin/bash

# Simple Auto-Pull Setup for Zora
# Only sets up automatic git pull - nothing else

APP_DIR="$HOME/zora"
UPDATE_SCRIPT="$HOME/update-zora.sh"
JOB_ID="1"
PERIOD_MS="300000"  # 5 minutes

echo "=== Setting Up Auto-Pull ==="

# Install termux-api if needed
if ! command -v termux-job-scheduler >/dev/null 2>&1; then
    echo "Installing termux-api..."
    pkg install -y termux-api
fi

# Create update script
cat > "$UPDATE_SCRIPT" << 'EOF'
#!/data/data/com.termux/files/usr/bin/sh

APP_DIR="$HOME/zora"
LOG="$HOME/auto-pull.log"

echo "[$(date)] Checking for updates..." >> "$LOG"

cd "$APP_DIR" || exit 1

# Skip if local changes exist
if ! git diff --quiet 2>/dev/null; then
    echo "[$(date)] Local changes found, skipping" >> "$LOG"
    exit 0
fi

# Fetch and check for updates
git fetch origin 2>/dev/null

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date)] Already up to date" >> "$LOG"
    exit 0
fi

# Pull updates
echo "[$(date)] Pulling updates..." >> "$LOG"
git pull --ff-only >> "$LOG" 2>&1

# Update requirements if exists
if [ -f "requirements.txt" ]; then
    ./venv/bin/pip install -r requirements.txt >> "$LOG" 2>&1
fi

echo "[$(date)] Update complete!" >> "$LOG"
EOF

chmod +x "$UPDATE_SCRIPT"
echo "✓ Update script created: $UPDATE_SCRIPT"

# Schedule the job
termux-job-scheduler --cancel --job-id "$JOB_ID" 2>/dev/null

if termux-job-scheduler \
    --job-id "$JOB_ID" \
    --period-ms "$PERIOD_MS" \
    --script "$UPDATE_SCRIPT" \
    --persisted true \
    --network any 2>/dev/null; then
    echo "✓ Auto-pull scheduled every 5 minutes"
else
    echo "✗ Failed! Make sure Termux:API app is installed from F-Droid"
    exit 1
fi

echo ""
echo "=== Auto-Pull Active ==="
echo "Check status:  termux-job-scheduler --pending"
echo "View logs:     cat ~/auto-pull.log"
echo "Test now:      ~/update-zora.sh"
echo "Cancel:        termux-job-scheduler --cancel --job-id 1"