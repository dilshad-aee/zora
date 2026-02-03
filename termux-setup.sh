#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Termux automation setup for Zora (auto-pull + restart)
# Usage:
#   Copy this file to Termux, then run:
#     bash termux-setup.sh
# Optional environment variables:
#   REPO_URL="git@github.com:user/repo.git"
#   APP_DIR="$HOME/zora"
#   SERVICE_NAME="zora"
#   START_CMD="./venv/bin/python run.py"
#   UPDATE_SCRIPT="$HOME/update-zora.sh"
#   JOB_ID="1"
#   PERIOD_MS="300000"   # 5 minutes
#   USE_SUBMODULES="0"   # set to 1 if your repo uses submodules

SERVICE_NAME="${SERVICE_NAME:-zora}"
APP_DIR="${APP_DIR:-$HOME/zora}"
REPO_URL="${REPO_URL:-}"
START_CMD="${START_CMD:-./venv/bin/python run.py}"
UPDATE_SCRIPT="${UPDATE_SCRIPT:-$HOME/update-zora.sh}"
JOB_ID="${JOB_ID:-1}"
PERIOD_MS="${PERIOD_MS:-300000}"
USE_SUBMODULES="${USE_SUBMODULES:-0}"

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

ensure_cmd() {
  local cmd="$1"
  local pkg="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    if command -v pkg >/dev/null 2>&1; then
      info "installing $pkg..."
      pkg install -y "$pkg"
    else
      die "pkg not found; install $pkg manually"
    fi
  fi
}

ensure_cmd git git
ensure_cmd python python
ensure_cmd ssh-keygen openssh
ensure_cmd sv termux-services
ensure_cmd termux-job-scheduler termux-api

if [ ! -d "$APP_DIR/.git" ]; then
  [ -n "$REPO_URL" ] || die "Repo not found at $APP_DIR. Set REPO_URL to clone."
  info "cloning repo into $APP_DIR..."
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

if [ ! -d "venv" ]; then
  info "creating virtualenv..."
  python -m venv venv
fi

if [ -f "requirements.txt" ]; then
  info "installing requirements..."
  ./venv/bin/pip install -r requirements.txt
else
  warn "requirements.txt not found; skipping pip install"
fi

SERVICE_DIR="$HOME/.termux/service/$SERVICE_NAME"
mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
cd "$APP_DIR"
exec $START_CMD
EOF
chmod +x "$SERVICE_DIR/run"

if command -v sv >/dev/null 2>&1; then
  sv up "$SERVICE_NAME" || true
fi

cat > "$UPDATE_SCRIPT" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -e
APP_DIR="$APP_DIR"
SERVICE_NAME="$SERVICE_NAME"
USE_SUBMODULES="$USE_SUBMODULES"

cd "\$APP_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "warning: local changes present; skipping update" >&2
  exit 0
fi

BRANCH=\$(git rev-parse --abbrev-ref HEAD)
REMOTE_REF="origin/\$BRANCH"

git fetch origin

if ! git show-ref --verify --quiet "refs/remotes/\$REMOTE_REF"; then
  echo "warning: remote branch \$REMOTE_REF not found; skipping update" >&2
  exit 0
fi

LOCAL=\$(git rev-parse HEAD)
REMOTE=\$(git rev-parse "\$REMOTE_REF")

if [ "\$LOCAL" = "\$REMOTE" ]; then
  exit 0
fi

git pull --ff-only

if [ "\$USE_SUBMODULES" = "1" ]; then
  git submodule update --init --recursive
fi

if [ -f "requirements.txt" ]; then
  ./venv/bin/pip install -r requirements.txt
fi

if command -v sv >/dev/null 2>&1; then
  sv restart "\$SERVICE_NAME"
else
  echo "warning: sv not found; restart manually" >&2
fi
EOF
chmod +x "$UPDATE_SCRIPT"

if command -v termux-job-scheduler >/dev/null 2>&1; then
  if termux-job-scheduler --job-id "$JOB_ID" --period-ms "$PERIOD_MS" --script "$UPDATE_SCRIPT" --persisted true; then
    info "scheduled update job id $JOB_ID every $PERIOD_MS ms"
  else
    warn "termux-job-scheduler failed. Make sure Termux:API app is installed."
  fi
else
  warn "termux-job-scheduler not found; install termux-api or use cron"
fi

info "done"
info "service status: sv status $SERVICE_NAME"
info "update script: $UPDATE_SCRIPT"
