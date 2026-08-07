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
CONTAINER_NAME="bigbikedata-sm-emulator"
IMAGE_NAME="sm-emulator"
EMULATOR_HOST="${SECRET_MANAGER_EMULATOR_HOST:-localhost:8083}"
PROJECT_ID="${GCP_PROJECT_ID:-local-test-project}"

# ---- Colour helpers ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_start() {
    log_info "Building emulator image..."
    podman build -t "$IMAGE_NAME" "$EMULATOR_DIR"

    # Clean up any old container
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true

    log_info "Starting emulator (host network mode)..."
    podman run -d --name "$CONTAINER_NAME" --network host \
        -e PORT=8083 "$IMAGE_NAME"

    log_info "Waiting for emulator to be healthy..."
    for i in $(seq 1 30); do
        if curl -s "http://${EMULATOR_HOST}/health" > /dev/null 2>&1; then
            log_info "Emulator is ready."
            break
        fi
        sleep 1
    done

    # Try to locate keys.env (auto-detect, then common locations)
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
        log_warn "keys.env not found — skipping seed step."
        log_warn "  The emulator may already have secrets from a previous run."
        log_warn "  To seed: create keys.env and run  $0 seed /path/to/keys.env"
    fi

    echo ""
    log_info "------------------------------------------------------"
    log_info "Emulators are running. Export these in your shell:"
    echo ""
    echo "  export SECRET_MANAGER_EMULATOR_HOST=${EMULATOR_HOST}"
    echo "  export GCP_PROJECT_ID=${PROJECT_ID}"
    echo ""
    log_info "Then start your app normally, e.g.:"
    echo "  python power_core/main.py"
    log_info "------------------------------------------------------"
}

cmd_stop() {
    log_info "Stopping emulator..."
    podman stop "$CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
    log_info "Emulator stopped."
}

cmd_seed() {
    log_info "(Re)seeding the Secret Manager emulator..."
    python "$EMULATOR_DIR/seed.py" --keys-env "$EMULATOR_DIR/keys.env"
}

cmd_env() {
    # Print export commands suitable for 'eval'
    echo "export SECRET_MANAGER_EMULATOR_HOST=${EMULATOR_HOST}"
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
    *)
        echo "Usage: $0 {start|stop|seed|env}"
        exit 1
        ;;
esac
