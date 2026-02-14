#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="${ZORA_ENV_FILE:-$HOME/.zora.env}"
if [ -f "$CONFIG_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
    set +a
fi

APP_DIR="${APP_DIR:-$HOME/zora}"
VENV_PYTHON="${VENV_PYTHON:-$APP_DIR/venv/bin/python}"
HOST="${ZORA_HOST:-0.0.0.0}"
PORT="${ZORA_PORT:-5001}"
PUBLIC_DOMAIN="${ZORA_PUBLIC_DOMAIN:-https://zora.crackery.in}"

BACKEND_LOG="${BACKEND_LOG:-$HOME/zora-backend.log}"
TUNNEL_LOG="${TUNNEL_LOG:-$HOME/zora-tunnel.log}"
BACKEND_PID_FILE="${BACKEND_PID_FILE:-$HOME/.zora-backend.pid}"
TUNNEL_PID_FILE="${TUNNEL_PID_FILE:-$HOME/.zora-tunnel.pid}"
BACKEND_STARTED_BY_SCRIPT=0

is_running() {
    local pid_file="$1"
    if [ ! -f "$pid_file" ]; then
        return 1
    fi

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [ -z "$pid" ]; then
        rm -f "$pid_file"
        return 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    rm -f "$pid_file"
    return 1
}

verify_started() {
    local pid_file="$1"
    local service_name="$2"
    local log_file="$3"

    sleep 1
    if is_running "$pid_file"; then
        return 0
    fi

    echo "${service_name} failed to start."
    if [ -f "$log_file" ]; then
        echo "Recent ${service_name} logs:"
        tail -n 20 "$log_file" || true
    fi
    return 1
}

start_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        echo "Backend already running (PID: $(cat "$BACKEND_PID_FILE"))"
        return
    fi

    if [ ! -x "$VENV_PYTHON" ]; then
        echo "Python not found at: $VENV_PYTHON"
        echo "Create venv first: python -m venv venv && ./venv/bin/pip install -r requirements.txt"
        exit 1
    fi

    cd "$APP_DIR"
    nohup env ZORA_HOST="$HOST" ZORA_PORT="$PORT" "$VENV_PYTHON" run.py > "$BACKEND_LOG" 2>&1 &
    echo "$!" > "$BACKEND_PID_FILE"
    if verify_started "$BACKEND_PID_FILE" "Backend" "$BACKEND_LOG"; then
        BACKEND_STARTED_BY_SCRIPT=1
        echo "Backend started on ${HOST}:${PORT} (PID: $(cat "$BACKEND_PID_FILE"))"
    else
        rm -f "$BACKEND_PID_FILE"
        exit 1
    fi
}

start_tunnel() {
    if is_running "$TUNNEL_PID_FILE"; then
        echo "Tunnel already running (PID: $(cat "$TUNNEL_PID_FILE"))"
        return
    fi

    if ! command -v cloudflared >/dev/null 2>&1; then
        echo "cloudflared is not installed. Install it in Termux first."
        exit 1
    fi

    if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
        nohup cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN" > "$TUNNEL_LOG" 2>&1 &
    elif [ -n "${CLOUDFLARE_TUNNEL_NAME:-}" ]; then
        nohup cloudflared tunnel run "$CLOUDFLARE_TUNNEL_NAME" > "$TUNNEL_LOG" 2>&1 &
    else
        echo "Set CLOUDFLARE_TUNNEL_NAME or CLOUDFLARE_TUNNEL_TOKEN before running."
        echo "Example: export CLOUDFLARE_TUNNEL_NAME=zora"
        exit 1
    fi

    echo "$!" > "$TUNNEL_PID_FILE"
    if verify_started "$TUNNEL_PID_FILE" "Cloudflare tunnel" "$TUNNEL_LOG"; then
        echo "Cloudflare tunnel started (PID: $(cat "$TUNNEL_PID_FILE"))"
    else
        rm -f "$TUNNEL_PID_FILE"
        if [ "$BACKEND_STARTED_BY_SCRIPT" -eq 1 ] && is_running "$BACKEND_PID_FILE"; then
            kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
            rm -f "$BACKEND_PID_FILE"
            echo "Stopped backend because tunnel startup failed."
        fi
        exit 1
    fi
}

echo "Starting Zora backend + Cloudflare tunnel..."
start_backend
start_tunnel

echo ""
echo "Done."
echo "Backend log: $BACKEND_LOG"
echo "Tunnel log:  $TUNNEL_LOG"
echo "App URL:     http://127.0.0.1:${PORT}"
echo "Public URL:  ${PUBLIC_DOMAIN}"
