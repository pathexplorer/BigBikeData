#!/bin/bash
# ---------------------------------------------------------------------------
# ngrok.sh — Ngrok public tunnel manager for local development.
#
# Local development uses the REAL Dropbox API + real webhook delivery, and
# Dropbox cannot reach localhost without a public tunnel. This module starts,
# stops, and reports the status of the ngrok tunnel container.
#
# Usage (standalone):
#   ./ngrok.sh start    # start the tunnel (prints public URL + Dropbox webhook)
#   ./ngrok.sh stop     # stop the tunnel
#   ./ngrok.sh status   # print the current public URL if the tunnel is up
#
# It is also sourced by local_dev.sh, which calls:
#   ngrok_tunnel_start
#   ngrok_tunnel_stop
#
# Requires NGROK_AUTHTOKEN from env or KDE Wallet (`kwallet-query`). The token
# is never written to disk in plaintext.
# ---------------------------------------------------------------------------
set -e

NGROK_CONTAINER_NAME="bigbikedata-ngrok"
NGROK_LOCAL_PORT="${NGROK_LOCAL_PORT:-8081}"
NGROK_IMAGE="docker.io/ngrok/ngrok:latest"

# ---- log helpers ----------------------------------------------------------
# local_dev.sh may already define these before sourcing this module; reuse them
# if present so output stays consistent. Fall back to plain echo when standalone.
if ! declare -F log_info >/dev/null 2>&1; then
    _NGROK_RED='\033[0;31m'
    _NGROK_GREEN='\033[0;32m'
    _NGROK_YELLOW='\033[1;33m'
    _NGROK_NC='\033[0m'
    log_info()  { echo -e "${_NGROK_GREEN}[INFO]${_NGROK_NC}  $*"; }
    log_warn()  { echo -e "${_NGROK_YELLOW}[WARN]${_NGROK_NC}  $*"; }
    log_error() { echo -e "${_NGROK_RED}[ERROR]${_NGROK_NC} $*"; }
fi

# ---- auth token resolution ------------------------------------------------
_resolve_authtoken() {
    # Prefer env, else fall back to KDE Wallet. Never stored to disk in plaintext.
    if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
        NGROK_AUTHTOKEN="$(kwallet-query -f net -r 'ngrok' kdewallet 2>/dev/null || echo '')"
    fi
    if [ -z "$NGROK_AUTHTOKEN" ]; then
        log_error "NGROK_AUTHTOKEN not set and not found in KDE wallet."
        log_error "  Export it:  export NGROK_AUTHTOKEN=your_token"
        log_error "  Or store in kwallet:  kwallet-query ..."
        return 1
    fi
}

# ---- Dropbox webhook path (optional) --------------------------------------
# If local_dev.sh exposes `_get_webhook_path`, use it to print the full webhook
# URL. Standalone, just print the raw public URL.
_webhook_hint() {
    if declare -F _get_webhook_path >/dev/null 2>&1; then
        echo "    Dropbox webhook:  ${1}$(_get_webhook_path)"
    fi
}

# ---- public API -----------------------------------------------------------
ngrok_tunnel_start() {
    # ngrok runs BY DEFAULT because local development uses the REAL Dropbox
    # API + real webhook delivery. Disable only if you use a Dropbox mock:
    #   NGROK_ENABLED=false ./local_dev.sh start
    if [ "${NGROK_ENABLED:-true}" != "true" ]; then
        log_info "Ngrok tunnel disabled (NGROK_ENABLED=false)."
        log_info "  This is only appropriate if you use a Dropbox mock instead of real webhooks."
        return 0
    fi

    _resolve_authtoken || return 1

    # Clean up any old ngrok container
    podman rm -f "$NGROK_CONTAINER_NAME" 2>/dev/null || true

    log_info "Pulling ngrok image..."
    podman pull "$NGROK_IMAGE"

    log_info "Starting ngrok tunnel (localhost:${NGROK_LOCAL_PORT})..."
    podman run -d --name "$NGROK_CONTAINER_NAME" --network host \
        -e NGROK_AUTHTOKEN="$NGROK_AUTHTOKEN" \
        "$NGROK_IMAGE" http "$NGROK_LOCAL_PORT"

    log_info "Waiting for ngrok to be ready..."
    sleep 3

    # Extract public URL from ngrok's local API
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

    if [ -n "$NGROK_URL" ]; then
        echo ""
        log_info "Ngrok tunnel is LIVE"
        echo "    Public URL:      ${NGROK_URL}"
        _webhook_hint "$NGROK_URL"
        echo ""
    else
        log_warn "Could not extract ngrok URL from API. Check: podman logs $NGROK_CONTAINER_NAME"
    fi
}

ngrok_tunnel_stop() {
    if podman inspect "$NGROK_CONTAINER_NAME" > /dev/null 2>&1; then
        log_info "Stopping ngrok tunnel..."
        podman stop "$NGROK_CONTAINER_NAME" 2>/dev/null || true
        podman rm -f "$NGROK_CONTAINER_NAME" 2>/dev/null || true
    fi
}

ngrok_tunnel_status() {
    if podman inspect "$NGROK_CONTAINER_NAME" > /dev/null 2>&1; then
        local url
        url=$(curl -s http://localhost:4040/api/tunnels | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")
        if [ -n "$url" ]; then
            log_info "Ngrok tunnel is LIVE: ${url}"
        else
            log_info "Ngrok container is running but no tunnel URL found yet."
        fi
    else
        log_info "Ngrok tunnel is not running."
    fi
}

# ---- standalone dispatch --------------------------------------------------
# Only dispatch when executed directly (not sourced), so local_dev.sh can call
# the functions above without triggering a subcommand.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-status}" in
        start)  ngrok_tunnel_start ;;
        stop)   ngrok_tunnel_stop ;;
        status) ngrok_tunnel_status ;;
        *)
            echo "Usage: $0 {start|stop|status}"
            exit 1
            ;;
    esac
fi
