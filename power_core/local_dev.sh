#!/bin/bash
# ---------------------------------------------------------------------------
# local_dev.sh — Start local development environment with emulators.
#
# ⚠️  Uses bare podman (not compose) due to rootless port-forwarding issues.
#     See gcp_actions/gcp_actions/emulators/secret_manager/SETUP_ISSUES.md
#
# Usage:
#   ./local_dev.sh start         # starts emulators and seeds them
#   ./local_dev.sh stop          # stops emulators
#   ./local_dev.sh seed          # (re)seed the Secret Manager emulator
#   ./local_dev.sh env           # print export commands for shell
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMULATOR_DIR="$SCRIPT_DIR/../../gcp_actions/gcp_actions/emulators/secret_manager"

# --- gocryptfs encrypted volume for emulator secrets ---
# Secrets never touch disk in plaintext.
# On first run, an encrypted directory + key file are created automatically.
EMULATOR_DATA="$SCRIPT_DIR/.emulator_data"           # mounted (decrypted) path
EMULATOR_DATA_ENC="$SCRIPT_DIR/.emulator_data.enc"   # encrypted storage on disk
EMULATOR_KEYFILE="$HOME/.config/bigbikedata/emulator.key"

CONTAINER_NAME="bigbikedata-sm-emulator"
IMAGE_NAME="sm-emulator"
EMULATOR_HOST="${SECRET_MANAGER_EMULATOR_HOST:-localhost:8083}"
PROJECT_ID="${GCP_PROJECT_ID:-local-test-project}"
NGROK_CONTAINER_NAME="bigbikedata-ngrok"
NGROK_LOCAL_PORT="${NGROK_LOCAL_PORT:-8081}"

# --- Firestore emulator ---
# Image: google/cloud-sdk:emulators includes the Firestore emulator + Java.
# Alternatives: google/cloud-sdk:latest (larger), or install gcloud CLI on host.
FS_CONTAINER_NAME="bigbikedata-fs-emulator"
FS_IMAGE="google/cloud-sdk:emulators"
FS_HOST="${FIRESTORE_EMULATOR_HOST:-localhost:8085}"
FS_PORT="${FS_HOST##*:}"
FS_DATA="$SCRIPT_DIR/.emulator_data_fs"          # persistent Firestore data (not encrypted)
FS_SEED_SCRIPT="$EMULATOR_DIR/../firestore/seed.py"

# Fetch webhook path from Secret Manager emulator (single source of truth).
# Requires emulator to be running and seeded.
_get_webhook_path() {
    local secret_name="${APP_JSON_KEYS:-fullstack-app-json-keys}"
    local emulator_base="http://${EMULATOR_HOST}"
    local path
    path=$(curl -s "${emulator_base}/v1/projects/${PROJECT_ID}/secrets/${secret_name}/versions/latest" 2>/dev/null \
        | python -c "import sys,json; d=json.load(sys.stdin); p=json.loads(d['payload']['data']); print(p.get('DROpbox_WEBHOOK_PATH',''))" 2>/dev/null)
    echo "${path:-/webhook}"
}

# ---- Colour helpers ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Ngrok tunnel helpers
# ---------------------------------------------------------------------------
tunnel_start() {
    if [ "${NGROK_ENABLED:-false}" != "true" ]; then
        log_info "Ngrok tunnel disabled (set NGROK_ENABLED=true to enable)."
        return 0
    fi

    # Auto-detect auth token from env or KDE wallet
    if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
        NGROK_AUTHTOKEN="$(kwallet-query -f net -r 'ngrok' kdewallet 2>/dev/null || echo '')"
    fi

    if [ -z "$NGROK_AUTHTOKEN" ]; then
        log_error "NGROK_AUTHTOKEN not set and not found in KDE wallet."
        log_error "  Export it:  export NGROK_AUTHTOKEN=your_token"
        log_error "  Or store in kwallet:  kwallet-query ..."
        return 1
    fi

    # Clean up any old ngrok container
    podman rm -f "$NGROK_CONTAINER_NAME" 2>/dev/null || true

    log_info "Pulling ngrok image..."
    podman pull docker.io/ngrok/ngrok:latest

    log_info "Starting ngrok tunnel (localhost:${NGROK_LOCAL_PORT})..."
    podman run -d --name "$NGROK_CONTAINER_NAME" --network host \
        -e NGROK_AUTHTOKEN="$NGROK_AUTHTOKEN" \
        docker.io/ngrok/ngrok http "$NGROK_LOCAL_PORT"

    log_info "Waiting for ngrok to be ready..."
    sleep 3

    # Extract public URL from ngrok's local API
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

    if [ -n "$NGROK_URL" ]; then
        echo ""
        log_info "Ngrok tunnel is LIVE"
        echo "    Public URL:      ${NGROK_URL}"
        echo "    Dropbox webhook:  ${NGROK_URL}$(_get_webhook_path)"
        echo ""
    else
        log_warn "Could not extract ngrok URL from API. Check: podman logs $NGROK_CONTAINER_NAME"
    fi
}

tunnel_stop() {
    if podman inspect "$NGROK_CONTAINER_NAME" > /dev/null 2>&1; then
        log_info "Stopping ngrok tunnel..."
        podman stop "$NGROK_CONTAINER_NAME" 2>/dev/null || true
        podman rm -f "$NGROK_CONTAINER_NAME" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Firestore emulator helpers
# ---------------------------------------------------------------------------
_wait_for_firestore() {
    log_info "Waiting for Firestore emulator on ${FS_HOST} ..."
    for i in $(seq 1 30); do
        # Firestore emulator is gRPC — check that the port is listening.
        if ss -tln | grep -q ":${FS_PORT}"; then
            log_info "Firestore emulator is ready."
            return 0
        fi
        sleep 1
    done
    log_error "Firestore emulator did not become ready in time."
    return 1
}

_seed_firestore() {
    # Seed only if the Firestore data dir is empty or doesn't exist.
    # The emulator persists data in --data-dir, so we seed once.
    local seed_marker="$FS_DATA/.seeded"
    if [ -f "$seed_marker" ]; then
        log_info "Firestore already seeded (marker found) — skipping."
        return 0
    fi

    log_info "Seeding Firestore emulator with initial config..."
    FIRESTORE_EMULATOR_HOST="${FS_HOST}" python "$FS_SEED_SCRIPT"
    if [ $? -eq 0 ]; then
        mkdir -p "$FS_DATA"
        touch "$seed_marker"
        log_info "Firestore seeded successfully."
    else
        log_error "Firestore seeding failed. Check that the emulator is running."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Encrypted volume helpers (gocryptfs)
# ---------------------------------------------------------------------------
_ensure_gocryptfs() {
    if ! command -v gocryptfs &>/dev/null; then
        log_error "gocryptfs is not installed. It's required for encrypted secret storage."
        log_error "  Install:  sudo apt install gocryptfs"
        log_error "  Or:       go install github.com/rfjakob/gocryptfs@latest"
        exit 1
    fi
}

_ensure_keyfile() {
    mkdir -p "$(dirname "$EMULATOR_KEYFILE")"
    if [ ! -f "$EMULATOR_KEYFILE" ]; then
        log_info "Generating encryption key (first run)..."
        dd if=/dev/urandom bs=32 count=1 status=none | base64 > "$EMULATOR_KEYFILE"
        chmod 600 "$EMULATOR_KEYFILE"
        log_info "Key stored at $EMULATOR_KEYFILE"
    fi
}

_mount_emulator_data() {
    _ensure_gocryptfs
    _ensure_keyfile

    if mountpoint -q "$EMULATOR_DATA" 2>/dev/null; then
        log_info "Encrypted volume already mounted at $EMULATOR_DATA"
        return 0
    fi

    mkdir -p "$EMULATOR_DATA"

    if [ ! -d "$EMULATOR_DATA_ENC" ]; then
        log_info "Initializing encrypted volume (first run)..."
        mkdir -p "$EMULATOR_DATA_ENC"
        gocryptfs -init -quiet -passfile "$EMULATOR_KEYFILE" "$EMULATOR_DATA_ENC"
    fi

    log_info "Mounting encrypted volume..."
    gocryptfs -quiet -passfile "$EMULATOR_KEYFILE" "$EMULATOR_DATA_ENC" "$EMULATOR_DATA"
    log_info "Encrypted volume mounted."
}

_unmount_emulator_data() {
    if mountpoint -q "$EMULATOR_DATA" 2>/dev/null; then
        log_info "Unmounting encrypted volume..."
        fusermount -u "$EMULATOR_DATA" 2>/dev/null || true
        log_info "Encrypted volume unmounted."
    fi
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_start() {
    log_info "Building emulator image..."
    podman build -t "$IMAGE_NAME" "$EMULATOR_DIR"

    # Clean up any old containers
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$FS_CONTAINER_NAME" 2>/dev/null || true

    # Mount encrypted volume (secrets survive restarts, never plaintext on disk)
    _mount_emulator_data

    # --- Firestore emulator ---
    log_info "Pulling Firestore emulator image (this may take a while on first run)..."
    podman pull "$FS_IMAGE"

    mkdir -p "$FS_DATA"
    log_info "Starting Firestore emulator (host network, data at ${FS_DATA})..."
    podman run -d --name "$FS_CONTAINER_NAME" --network host \
        -v "$FS_DATA:/data:Z" \
        "$FS_IMAGE" \
        gcloud beta emulators firestore start --host-port="0.0.0.0:${FS_PORT}" --data-dir=/data

    _wait_for_firestore

    # --- Secret Manager emulator ---
    log_info "Starting emulator (host network, encrypted volume)..."
    podman run -d --name "$CONTAINER_NAME" --network host \
        -e PORT=8083 \
        -v "$EMULATOR_DATA:/data:Z" \
        "$IMAGE_NAME"

    log_info "Waiting for emulator to be healthy..."
    for i in $(seq 1 30); do
        if curl -s "http://${EMULATOR_HOST}/health" > /dev/null 2>&1; then
            log_info "Emulator is ready."
            break
        fi
        sleep 1
    done

    # Seed only if emulator data is empty AND keys.env exists
    if [ ! -f "$EMULATOR_DATA/secrets.json" ] || [ "$(cat "$EMULATOR_DATA/secrets.json" 2>/dev/null)" = "{}" ]; then
        KEYS_ENV_FILE=""
        for candidate in \
            "$EMULATOR_DIR/keys.env" \
            "$SCRIPT_DIR/power_core/project_env/keys.env" \
            "$SCRIPT_DIR/project_env/keys.env"; do
            if [ -f "$candidate" ]; then
                KEYS_ENV_FILE="$candidate"
                break
            fi
        done

        if [ -n "$KEYS_ENV_FILE" ]; then
            log_info "Seeding secrets into emulator from $KEYS_ENV_FILE ..."
            python "$EMULATOR_DIR/seed.py" --keys-env "$KEYS_ENV_FILE"
        else
            log_warn "Emulator data is empty and no keys.env found."
            log_warn "  Seed once:  $0 seed /path/to/keys.env"
            log_warn "  Secrets will then persist in the encrypted volume."
        fi
    else
        log_info "Emulator already has secrets (from encrypted volume) — skipping seed."
    fi

    # Seed Firestore after it's ready
    _seed_firestore

    tunnel_start

    echo ""
    log_info "------------------------------------------------------"
    log_info "All emulators are running."
    log_info ""
    log_info "  ✅ Secret Manager  : ${EMULATOR_HOST}"
    log_info "  ✅ Firestore        : ${FS_HOST}"
    log_info "  ✅ Encrypted volume : mounted"
    log_info ""
    log_info "The app reads all config from local_config.json + emulators."
    log_info "No manual exports needed. Just run:"
    echo ""
    echo "  .venv/bin/python power_core/main.py"
    log_info "------------------------------------------------------"
}

cmd_stop() {
    tunnel_stop

    log_info "Stopping Firestore emulator..."
    podman stop "$FS_CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$FS_CONTAINER_NAME" 2>/dev/null || true

    log_info "Stopping Secret Manager emulator..."
    podman stop "$CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true

    _unmount_emulator_data

    log_info "All emulators stopped."
}

cmd_seed() {
    log_info "(Re)seeding the Secret Manager emulator..."
    python "$EMULATOR_DIR/seed.py" --keys-env "$EMULATOR_DIR/keys.env"
}

cmd_env() {
    # Print export commands suitable for 'eval'
    echo "export SECRET_MANAGER_EMULATOR_HOST=${EMULATOR_HOST}"
    echo "export FIRESTORE_EMULATOR_HOST=${FS_HOST}"
    echo "export GCP_PROJECT_ID=${PROJECT_ID}"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "${1:-start}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    seed)   cmd_seed ;;
    env)    cmd_env ;;
    tunnel) tunnel_start ;;
    *)
        echo "Usage: $0 {start|stop|seed|env|tunnel}"
        exit 1
        ;;
esac
