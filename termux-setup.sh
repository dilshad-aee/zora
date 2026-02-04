#!/data/data/com.termux/files/usr/bin/bash

#############################################
# ZORA - Complete Termux Setup Script
# For Android Termux Server
#############################################

# Exit on undefined variables only (not on errors - we handle those manually)
set -u

# ==================== CONFIGURATION ====================
SERVICE_NAME="zora"
APP_DIR="$HOME/zora"
START_CMD="./venv/bin/python run.py"
UPDATE_SCRIPT="$HOME/update-zora.sh"
JOB_ID="1"
PERIOD_MS="300000"  # 5 minutes
USE_SUBMODULES="0"
HOST="0.0.0.0"
PORT="5000"

# ==================== COLORS ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ==================== HELPER FUNCTIONS ====================
info() { 
    echo -e "${GREEN}[INFO]${NC} $*"
}

warn() { 
    echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

error() { 
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

success() {
    echo -e "${CYAN}[SUCCESS]${NC} $*"
}

header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE} $*${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Check if running in Termux
check_termux() {
    if [ ! -d "/data/data/com.termux" ]; then
        error "This script must be run in Termux!"
        exit 1
    fi
    info "Running in Termux environment ✓"
}

# Install package if command not found
install_if_missing() {
    local cmd="$1"
    local pkg="${2:-$1}"
    
    if ! command -v "$cmd" >/dev/null 2>&1; then
        info "Installing $pkg..."
        pkg install -y "$pkg" 2>/dev/null || {
            error "Failed to install $pkg"
            return 1
        }
        success "$pkg installed"
    else
        info "$cmd already installed ✓"
    fi
}

# ==================== MAIN SETUP ====================

header "ZORA TERMUX SETUP"
echo "Starting setup at $(date)"
echo ""

# Step 1: Check environment
header "Step 1: Checking Environment"
check_termux

# Step 2: Update package list
header "Step 2: Updating Package List"
info "Running pkg update..."
pkg update -y 2>/dev/null || warn "pkg update had issues, continuing..."
success "Package list updated"

# Step 3: Install required packages
header "Step 3: Installing Required Packages"

PACKAGES="python git termux-services termux-api openssh"
for pkg in $PACKAGES; do
    case $pkg in
        python)
            install_if_missing python python
            ;;
        git)
            install_if_missing git git
            ;;
        termux-services)
            install_if_missing sv termux-services
            ;;
        termux-api)
            install_if_missing termux-job-scheduler termux-api
            ;;
        openssh)
            install_if_missing ssh openssh
            ;;
    esac
done

# Step 4: Ensure termux-services is running
header "Step 4: Setting Up Termux Services"

# Source the service environment
if [ -f "$PREFIX/etc/profile.d/start-services.sh" ]; then
    source "$PREFIX/etc/profile.d/start-services.sh" 2>/dev/null || true
fi

# Check if runsvdir is running
if ! pgrep -x runsvdir >/dev/null 2>&1; then
    warn "runsvdir not running. Starting services..."
    
    # Try to start it
    if [ -x "$PREFIX/share/termux-services/svlogger" ]; then
        nohup runsvdir -P "$PREFIX/var/service" > /dev/null 2>&1 &
        sleep 2
    fi
    
    if pgrep -x runsvdir >/dev/null 2>&1; then
        success "runsvdir started"
    else
        warn "Could not start runsvdir automatically"
        warn "Please restart Termux and run this script again"
        warn "Or run: sv-enable $SERVICE_NAME"
    fi
else
    success "runsvdir is running ✓"
fi

# Step 5: Navigate to app directory
header "Step 5: Setting Up Application Directory"

if [ ! -d "$APP_DIR" ]; then
    error "App directory $APP_DIR does not exist!"
    error "Please clone your repository first or create the directory"
    exit 1
fi

cd "$APP_DIR" || {
    error "Cannot change to $APP_DIR"
    exit 1
}
success "Changed to $APP_DIR ✓"

# Step 6: Setup Python virtual environment
header "Step 6: Setting Up Python Environment"

if [ ! -d "venv" ]; then
    info "Creating virtual environment..."
    python -m venv venv || {
        error "Failed to create virtual environment"
        exit 1
    }
    success "Virtual environment created"
else
    success "Virtual environment exists ✓"
fi

# Upgrade pip
info "Upgrading pip..."
./venv/bin/python -m pip install --upgrade pip 2>/dev/null || warn "pip upgrade failed"

# Step 7: Install Python requirements
header "Step 7: Installing Python Requirements"

if [ -f "requirements.txt" ]; then
    info "Installing requirements from requirements.txt..."
    ./venv/bin/pip install -r requirements.txt || {
        warn "Some requirements failed to install"
    }
    success "Requirements installed"
else
    warn "requirements.txt not found, skipping..."
fi

# Step 8: Create the service
header "Step 8: Creating Termux Service"

SERVICE_DIR="$PREFIX/var/service/$SERVICE_NAME"
LOG_DIR="$SERVICE_DIR/log"
LOG_MAIN="$LOG_DIR/main"

info "Service directory: $SERVICE_DIR"

# Create service directory
mkdir -p "$SERVICE_DIR"
mkdir -p "$LOG_MAIN"

# Create main run script
cat > "$SERVICE_DIR/run" << RUNEOF
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
cd "$APP_DIR" || exit 1
export FLASK_APP=run.py
export FLASK_ENV=production
export HOST=$HOST
export PORT=$PORT
exec ./venv/bin/python run.py
RUNEOF

chmod +x "$SERVICE_DIR/run"
success "Main run script created"

# Create log run script
cat > "$LOG_DIR/run" << LOGEOF
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt "$LOG_MAIN"
LOGEOF

chmod +x "$LOG_DIR/run"
success "Log script created"

# Create finish script (runs when service stops)
cat > "$SERVICE_DIR/finish" << FINEOF
#!/data/data/com.termux/files/usr/bin/sh
echo "Service $SERVICE_NAME stopped at \$(date)" >> "$LOG_MAIN/current"
sleep 1
FINEOF

chmod +x "$SERVICE_DIR/finish"
success "Finish script created"

# Step 9: Wait for service detection
header "Step 9: Waiting for Service Detection"

info "Waiting for supervisor to detect the service..."
WAIT_COUNT=0
MAX_WAIT=10

while [ ! -d "$SERVICE_DIR/supervise" ] && [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    echo -n "."
done
echo ""

if [ -d "$SERVICE_DIR/supervise" ]; then
    success "Service detected by supervisor"
else
    warn "Service not yet detected - this is normal on first run"
    warn "It will be available after Termux restart"
fi

# Step 10: Start the service
header "Step 10: Starting Service"

sleep 2

if command -v sv >/dev/null 2>&1; then
    # Try to start
    if sv status "$SERVICE_NAME" 2>/dev/null; then
        info "Service status retrieved, attempting to start..."
        sv up "$SERVICE_NAME" 2>/dev/null && success "Service started" || warn "Service start pending"
    else
        warn "Service not yet available to supervisor"
        info "Will be available after Termux restart"
    fi
else
    warn "sv command not found"
fi

# Step 11: Create update script
header "Step 11: Creating Auto-Update Script"

cat > "$UPDATE_SCRIPT" << 'UPDATEEOF'
#!/data/data/com.termux/files/usr/bin/sh
set -e

APP_DIR="$HOME/zora"
SERVICE_NAME="zora"
LOG_FILE="$HOME/zora-update.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log "Starting update check..."

cd "$APP_DIR" || {
    log "ERROR: Cannot cd to $APP_DIR"
    exit 1
}

# Check for local changes
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    log "WARNING: Local changes present, skipping update"
    exit 0
fi

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || {
    log "ERROR: Cannot get branch"
    exit 1
}

# Fetch updates
git fetch origin 2>/dev/null || {
    log "ERROR: Cannot fetch from origin"
    exit 1
}

# Compare local and remote
LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null) || {
    log "WARNING: Cannot find remote branch origin/$BRANCH"
    exit 0
}

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date"
    exit 0
fi

log "Updates found, pulling..."

# Pull changes
git pull --ff-only origin "$BRANCH" 2>/dev/null || {
    log "ERROR: Pull failed"
    exit 1
}

# Update requirements if changed
if [ -f "requirements.txt" ]; then
    log "Updating requirements..."
    ./venv/bin/pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || true
fi

# Restart service
if command -v sv >/dev/null 2>&1; then
    log "Restarting service..."
    sv restart "$SERVICE_NAME" 2>/dev/null || log "WARNING: Restart failed"
fi

log "Update complete"
UPDATEEOF

chmod +x "$UPDATE_SCRIPT"
success "Update script created at $UPDATE_SCRIPT"

# Step 12: Schedule auto-updates (optional)
header "Step 12: Scheduling Auto-Updates"

if command -v termux-job-scheduler >/dev/null 2>&1; then
    info "Setting up scheduled updates..."
    
    # Cancel existing job first
    termux-job-scheduler --cancel --job-id "$JOB_ID" 2>/dev/null || true
    
    # Schedule new job
    if termux-job-scheduler \
        --job-id "$JOB_ID" \
        --period-ms "$PERIOD_MS" \
        --script "$UPDATE_SCRIPT" \
        --persisted true \
        --network any 2>/dev/null; then
        success "Auto-update scheduled (every 5 minutes)"
    else
        warn "Job scheduler failed - make sure Termux:API app is installed"
    fi
else
    warn "termux-job-scheduler not available"
    info "Install Termux:API app from F-Droid for auto-updates"
fi

# Step 13: Create helper scripts
header "Step 13: Creating Helper Scripts"

# Start script
cat > "$HOME/start-zora.sh" << 'STARTEOF'
#!/data/data/com.termux/files/usr/bin/sh
sv up zora
echo "Zora service started"
sv status zora
STARTEOF
chmod +x "$HOME/start-zora.sh"

# Stop script  
cat > "$HOME/stop-zora.sh" << 'STOPEOF'
#!/data/data/com.termux/files/usr/bin/sh
sv down zora
echo "Zora service stopped"
STOPEOF
chmod +x "$HOME/stop-zora.sh"

# Status script
cat > "$HOME/status-zora.sh" << 'STATUSEOF'
#!/data/data/com.termux/files/usr/bin/sh
echo "=== Service Status ==="
sv status zora 2>/dev/null || echo "Service not running"
echo ""
echo "=== Recent Logs ==="
LOG_FILE="$PREFIX/var/service/zora/log/main/current"
if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
else
    echo "No logs yet"
fi
STATUSEOF
chmod +x "$HOME/status-zora.sh"

# Logs script
cat > "$HOME/logs-zora.sh" << 'LOGSEOF'
#!/data/data/com.termux/files/usr/bin/sh
LOG_FILE="$PREFIX/var/service/zora/log/main/current"
if [ -f "$LOG_FILE" ]; then
    tail -f "$LOG_FILE"
else
    echo "No logs yet. Service might not have started."
fi
LOGSEOF
chmod +x "$HOME/logs-zora.sh"

# Restart script
cat > "$HOME/restart-zora.sh" << 'RESTARTEOF'
#!/data/data/com.termux/files/usr/bin/sh
sv restart zora
echo "Zora service restarted"
sv status zora
RESTARTEOF
chmod +x "$HOME/restart-zora.sh"

# Manual run script (for debugging)
cat > "$HOME/run-zora-manual.sh" << MANUALEOF
#!/data/data/com.termux/files/usr/bin/sh
cd "$APP_DIR"
echo "Starting Zora manually (Ctrl+C to stop)..."
./venv/bin/python run.py
MANUALEOF
chmod +x "$HOME/run-zora-manual.sh"

success "Helper scripts created"

# Step 14: Create .bashrc additions
header "Step 14: Setting Up Shell Aliases"

BASHRC_ADDITIONS='
# Zora aliases
alias zora-start="sv up zora"
alias zora-stop="sv down zora"
alias zora-restart="sv restart zora"
alias zora-status="sv status zora"
alias zora-logs="tail -f $PREFIX/var/service/zora/log/main/current"
alias zora-cd="cd ~/zora"
'

if ! grep -q "Zora aliases" "$HOME/.bashrc" 2>/dev/null; then
    echo "$BASHRC_ADDITIONS" >> "$HOME/.bashrc"
    success "Aliases added to .bashrc"
else
    info "Aliases already in .bashrc ✓"
fi

# ==================== FINAL SUMMARY ====================
header "SETUP COMPLETE!"

echo ""
echo -e "${GREEN}Your Zora server is now configured!${NC}"
echo ""
echo -e "${CYAN}=== Quick Commands ===${NC}"
echo "  Start:    ~/start-zora.sh   or  sv up zora"
echo "  Stop:     ~/stop-zora.sh    or  sv down zora"
echo "  Restart:  ~/restart-zora.sh or  sv restart zora"
echo "  Status:   ~/status-zora.sh  or  sv status zora"
echo "  Logs:     ~/logs-zora.sh    or  tail -f \$PREFIX/var/service/zora/log/main/current"
echo "  Manual:   ~/run-zora-manual.sh (for debugging)"
echo ""
echo -e "${CYAN}=== Important Paths ===${NC}"
echo "  App directory:     $APP_DIR"
echo "  Service directory: $SERVICE_DIR"
echo "  Update script:     $UPDATE_SCRIPT"
echo "  Update log:        $HOME/zora-update.log"
echo ""
echo -e "${CYAN}=== Access Your Server ===${NC}"
echo "  Local:    http://localhost:$PORT"
echo "  Network:  http://$(ip route get 1 2>/dev/null | awk '{print $7;exit}' || echo "YOUR_IP"):$PORT"
echo ""
echo -e "${YELLOW}=== First Time Setup ===${NC}"
echo "  If service doesn't start, please:"
echo "  1. Close Termux completely (swipe away)"
echo "  2. Reopen Termux"
echo "  3. Run: sv up zora"
echo ""
echo -e "${GREEN}=== To Run Manually Now ===${NC}"
echo "  cd ~/zora && ./venv/bin/python run.py"
echo ""

# Try to show current status
if command -v sv >/dev/null 2>&1; then
    echo -e "${CYAN}=== Current Service Status ===${NC}"
    sv status "$SERVICE_NAME" 2>/dev/null || echo "  Service will be available after Termux restart"
fi

echo ""
success "Setup completed at $(date)"
echo ""