#!/bin/bash
# ---------------------------------------------------------------------------
# local_dev.sh — Start local development environment with emulators.
#
# ⚠️  Uses bare podman (not compose) due to rootless port-forwarding issues.
#     See gcp_actions/gcp_actions/emulators/secret_manager/SETUP_ISSUES.md
#
# All emulators run inside a single podman *pod* (shared network namespace).
# Ports are published on the pod — no per-container port management needed.
#
# Usage:
#   ./local_dev.sh start [--project emulator|dev|prod] [--from-gcp]  # start emulators
#   ./local_dev.sh stop               # stop emulators
#   ./local_dev.sh seed               # (re)seed the Secret Manager emulator
#   ./local_dev.sh env                # print export commands for shell
#   ./local_dev.sh tunnel             # start only the ngrok tunnel (see ngrok.sh)
#   ./local_dev.sh rotate-webhook     # generate new DROpbox_WEBHOOK_PATH (preserves all other secrets)
#
# Note: ngrok tunnel logic is in ./ngrok.sh (sourced by this script).
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMULATOR_DIR="$SCRIPT_DIR/../../gcp_actions/gcp_actions/emulators/secret_manager"

# Handle --from-gcp flag
FROM_GCP=""
for arg in "$@"; do
    case "$arg" in
        --from-gcp) FROM_GCP="1" ;;
    esac
done

# --- gocryptfs encrypted volume for emulator secrets ---
# Secrets never touch disk in plaintext.
# On first run, an encrypted directory + key file are created automatically.
EMULATOR_DATA="$SCRIPT_DIR/.emulator_data"           # mounted (decrypted) path
EMULATOR_DATA_ENC="$SCRIPT_DIR/.emulator_data.enc"   # encrypted storage on disk
EMULATOR_KEYFILE="$HOME/.config/bigbikedata/emulator.key"

CONTAINER_NAME="bigbikedata-sm-emulator"
IMAGE_NAME="sm-emulator"
EMULATOR_HOST="${SECRET_MANAGER_EMULATOR_HOST:-127.0.0.1:8083}"
SM_PORT="${EMULATOR_HOST##*:}"
PROJECT_ID="${GCP_PROJECT_ID:-local-test-project}"
POD_NAME="bigbikedata-dev"

# --- Firestore emulator ---
# Image: docker.io/google/cloud-sdk:emulators includes the Firestore emulator + Java.
# Alternatives: docker.io/google/cloud-sdk:latest (larger), or install gcloud CLI on host.
FS_CONTAINER_NAME="bigbikedata-fs-emulator"
FS_IMAGE="docker.io/google/cloud-sdk:emulators"
FS_HOST="${FIRESTORE_EMULATOR_HOST:-127.0.0.1:8085}"
FS_PORT="${FS_HOST##*:}"
FS_DATA="$SCRIPT_DIR/.emulator_data_fs"          # persistent Firestore data (not encrypted)
FS_SEED_SCRIPT="$EMULATOR_DIR/../firestore/seed.py"

# --- Pub/Sub emulator ---
# Runs the Google Pub/Sub emulator inside the same pod (shared network namespace).
# Previously Pub/Sub was started manually and NOT attached to the pod, which broke
# the pipeline's publish_to_pubsub step. It is now a first-class emulator here.
PS_CONTAINER_NAME="bigbikedata-ps-emulator"
PS_IMAGE="docker.io/google/cloud-sdk:emulators"   # same image as Firestore (already pulled)
PS_HOST="${PUBSUB_EMULATOR_HOST:-127.0.0.1:8086}"
PS_PORT="${PS_HOST##*:}"
# Push subscription target — the local backend process running outside the pod.
PS_PUSH_ENDPOINT="${PUBSUB_PUSH_ENDPOINT:-http://localhost:8081/private-processing-handler}"
PS_TOPIC_NAME="${PUBSUB_TOPIC_NAME:-${DROPBOX_TOPIC_NAME:-dropbox-handler-testing}}"
PS_SUBSCRIPTION_NAME="${PUBSUB_SUBSCRIPTION_NAME:-local-processing-sub}"

# --- Python interpreter ---
# The Pub/Sub client library (google-cloud-pubsub) lives in the project venv,
# not the system python. Prefer the venv interpreter for seeding scripts.
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_BIN="python"
fi

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
# Pod helpers
# ---------------------------------------------------------------------------
_ensure_pod() {
    if podman pod exists "$POD_NAME" 2>/dev/null; then
        local pod_state
        pod_state=$(podman pod inspect "$POD_NAME" --format '{{.State}}' 2>/dev/null)
        if [ "$pod_state" = "Running" ]; then
            log_info "Pod '$POD_NAME' is already running."
            return 0
        fi
        log_info "Removing stopped pod '$POD_NAME'..."
        podman pod rm -f "$POD_NAME" 2>/dev/null || true
    fi

    log_info "Creating pod '$POD_NAME' (ports: ${SM_PORT}, ${FS_PORT}, ${PS_PORT})..."
    podman pod create \
        --name "$POD_NAME" \
        -p "${SM_PORT}:${SM_PORT}" \
        -p "${FS_PORT}:${FS_PORT}" \
        -p "${PS_PORT}:${PS_PORT}"
    log_info "Pod created. Published ports: ${SM_PORT} (Secret Manager), ${FS_PORT} (Firestore), ${PS_PORT} (Pub/Sub)."
}

# ---------------------------------------------------------------------------
# Ngrok tunnel helpers (module)
# ---------------------------------------------------------------------------
# Ngrok is a dedicated module so it can be reused/run independently.
# source ngrok.sh defines: ngrok_tunnel_start, ngrok_tunnel_stop, ngrok_tunnel_status
source "$SCRIPT_DIR/ngrok.sh"

# ---------------------------------------------------------------------------
# Firestore emulator helpers
# ---------------------------------------------------------------------------
_wait_for_firestore() {
    log_info "Waiting for Firestore emulator on ${FS_HOST} ..."
    for i in $(seq 1 60); do
        # Check if the container is still running
        if ! podman inspect "$FS_CONTAINER_NAME" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
            log_error "Firestore container exited unexpectedly. Last 20 log lines:"
            podman logs "$FS_CONTAINER_NAME" 2>&1 | tail -20
            return 1
        fi

        # Check for the Firestore emulator startup message
        if podman logs "$FS_CONTAINER_NAME" 2>&1 | grep -qE "(Dev App Server is now running|running on|started|listening)"; then
            log_info "Firestore emulator is ready."
            return 0
        fi

        # Show progress every 15 seconds
        if [ $((i % 15)) -eq 0 ]; then
            log_info "  Still waiting... (${i}s) — last log line:"
            podman logs "$FS_CONTAINER_NAME" 2>&1 | tail -1
        fi
        sleep 1
    done
    log_error "Firestore emulator did not become ready in 60s. Last 20 log lines:"
    podman logs "$FS_CONTAINER_NAME" 2>&1 | tail -20
    return 1
}

_seed_firestore() {
    local from_gcp="${1:-}"

    if [ -n "$from_gcp" ]; then
        # Verify GCP auth before attempting pull
        if ! gcloud auth application-default print-access-token &>/dev/null; then
            log_error "Not authenticated to GCP. Run: gcloud auth application-default login"
            log_error "Falling back to built-in defaults (6 placeholder keys)."
            FIRESTORE_EMULATOR_HOST="${FS_HOST}" "$PYTHON_BIN" "$FS_SEED_SCRIPT"
            return 0
        fi

        log_info "Pulling Firestore config from GCP..."
        FIRESTORE_EMULATOR_HOST="${FS_HOST}" "$PYTHON_BIN" "$FS_SEED_SCRIPT" --from-project
        if [ $? -eq 0 ]; then
            log_info "✅ Firestore seeded from GCP."
        else
            echo ""
            log_error "=============================================="
            log_error "  GCP PULL FAILED — using placeholder defaults."
            log_error "  Your Firestore emulator has 6 dummy keys."
            log_error ""
            log_error "  To fix:"
            log_error "  1. gcloud auth application-default login"
            log_error "  2. Verify the document exists in GCP:"
            log_error "     gcloud firestore documents describe config/local/settings/data"
            log_error "  3. Re-run: $0 start --from-gcp"
            log_error "=============================================="
            echo ""
            FIRESTORE_EMULATOR_HOST="${FS_HOST}" "$PYTHON_BIN" "$FS_SEED_SCRIPT"
        fi
        return 0
    fi

    log_info "Seeding Firestore emulator with built-in defaults..."
    FIRESTORE_EMULATOR_HOST="${FS_HOST}" "$PYTHON_BIN" "$FS_SEED_SCRIPT"
    if [ $? -eq 0 ]; then
        log_info "Firestore seeded (built-in defaults)."
        log_info "  To pull real config from GCP next time, use: $0 start --from-gcp"
    else
        log_error "Firestore seeding failed."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Pub/Sub emulator helpers
# ---------------------------------------------------------------------------
_wait_for_pubsub() {
    log_info "Waiting for Pub/Sub emulator on ${PS_HOST} ..."
    for i in $(seq 1 60); do
        if ! podman inspect "$PS_CONTAINER_NAME" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
            log_error "Pub/Sub container exited unexpectedly. Last 20 log lines:"
            podman logs "$PS_CONTAINER_NAME" 2>&1 | tail -20
            return 1
        fi
        # The emulator logs "running on" once ready.
        if podman logs "$PS_CONTAINER_NAME" 2>&1 | grep -qE "(running on|started|listening)"; then
            log_info "Pub/Sub emulator is ready."
            return 0
        fi
        if [ $((i % 15)) -eq 0 ]; then
            log_info "  Still waiting... (${i}s) — last log line:"
            podman logs "$PS_CONTAINER_NAME" 2>&1 | tail -1
        fi
        sleep 1
    done
    log_error "Pub/Sub emulator did not become ready in 60s. Last 20 log lines:"
    podman logs "$PS_CONTAINER_NAME" 2>&1 | tail -20
    return 1
}

# Creates the Pub/Sub topic + push subscription pointing at the local backend.
_seed_pubsub() {
    log_info "Setting up Pub/Sub topic '${PS_TOPIC_NAME}' and push subscription '${PS_SUBSCRIPTION_NAME}'..."
    PUBSUB_EMULATOR_HOST="${PS_HOST}" "$PYTHON_BIN" - "$PS_TOPIC_NAME" "$PS_SUBSCRIPTION_NAME" "$PS_PUSH_ENDPOINT" <<'PYEOF'
import sys
from google.cloud import pubsub_v1
from google.api_core.exceptions import AlreadyExists

topic_name, sub_name, push_endpoint = sys.argv[1], sys.argv[2], sys.argv[3]
project_id = __import__('os').environ.get('GCP_PROJECT_ID', 'local-test-project')

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()
topic_path = publisher.topic_path(project_id, topic_name)
sub_path = subscriber.subscription_path(project_id, sub_name)

try:
    publisher.create_topic(name=topic_path)
    print(f"✅ Topic created: {topic_name}")
except AlreadyExists:
    print(f"✅ Topic already exists: {topic_name}")

try:
    subscriber.create_subscription(
        name=sub_path,
        topic=topic_path,
        push_config=pubsub_v1.types.PushConfig(push_endpoint=push_endpoint),
        ack_deadline_seconds=600,
    )
    print(f"✅ Subscription created: {sub_name} -> {push_endpoint}")
except AlreadyExists:
    print(f"✅ Subscription already exists: {sub_name}")
except Exception as e:
    print(f"⚠️  Could not create subscription (may need backend running): {e}")
PYEOF
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
    # Load project-specific configuration
    case "$PROJECT_MODE" in
        dev)
            log_info "Loading dev project configuration..."
            if [ -f "$SCRIPT_DIR/../../local_config.dev.json" ]; then
                export $(cat "$SCRIPT_DIR/../../local_config.dev.json" | python -c "import sys, json; d=json.load(sys.stdin); print(' '.join(f'{k}={v}' for k,v in d.items()))")
            else
                log_warn "local_config.dev.json not found, using defaults"
            fi
            ;;
        prod)
            log_info "Loading prod project configuration..."
            if [ -f "$SCRIPT_DIR/../../local_config.json" ]; then
                export $(cat "$SCRIPT_DIR/../../local_config.json" | python -c "import sys, json; d=json.load(sys.stdin); print(' '.join(f'{k}={v}' for k,v in d.items()))")
            else
                log_warn "local_config.json not found, using defaults"
            fi
            ;;
        emulator|*)
            log_info "Using emulator configuration (default)..."
            if [ -f "$SCRIPT_DIR/../../local_config.json" ]; then
                export $(cat "$SCRIPT_DIR/../../local_config.json" | python -c "import sys, json; d=json.load(sys.stdin); print(' '.join(f'{k}={v}' for k,v in d.items()))")
            fi
            ;;
    esac

    log_info "Building emulator image..."
    podman build -t "$IMAGE_NAME" "$EMULATOR_DIR"

    # Clean up any old containers and pod
    podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$FS_CONTAINER_NAME" 2>/dev/null || true
    podman rm -f "$PS_CONTAINER_NAME" 2>/dev/null || true
    podman pod rm -f "$POD_NAME" 2>/dev/null || true

    # Mount encrypted volume (secrets survive restarts, never plaintext on disk)
    _mount_emulator_data

    # Create pod — all emulator ports are published here (single source of truth)
    _ensure_pod

    # --- Firestore emulator ---
    log_info "Pulling Firestore emulator image (this may take a while on first run)..."
    podman pull "$FS_IMAGE"

    mkdir -p "$FS_DATA"
    log_info "Starting Firestore emulator (pod: ${POD_NAME})..."
    podman run -d --name "$FS_CONTAINER_NAME" --pod "$POD_NAME" \
        "$FS_IMAGE" \
        gcloud beta emulators firestore start --host-port="0.0.0.0:${FS_PORT}"

    _wait_for_firestore

    # --- Secret Manager emulator ---
    log_info "Starting Secret Manager emulator (pod: ${POD_NAME}, encrypted volume)..."
    podman run -d --name "$CONTAINER_NAME" --pod "$POD_NAME" \
        -e PORT="${SM_PORT}" \
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

    # --- Pub/Sub emulator ---
    log_info "Starting Pub/Sub emulator (pod: ${POD_NAME})..."
    podman run -d --name "$PS_CONTAINER_NAME" --pod "$POD_NAME" \
        "$PS_IMAGE" \
        gcloud beta emulators pubsub start --host-port="0.0.0.0:${PS_PORT}"

    _wait_for_pubsub

    # Create the topic + push subscription for the pipeline.
    # Non-fatal: if seeding fails, the emulators still start and ngrok still
    # comes up — the topic can be created later via create_pubsub_emu.py.
    _seed_pubsub || log_warn "Pub/Sub topic/subscription setup failed (will not block startup)."

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
            python "$EMULATOR_DIR/seed.py" --keys-env "$KEYS_ENV_FILE" && SEEDED_SECRETS="1"
        else
            log_warn "Emulator data is empty and no keys.env found."
            log_warn "  Seed once:  $0 seed /path/to/keys.env"
            log_warn "  Secrets will then persist in the encrypted volume."
        fi
    else
        log_info "Emulator already has secrets (from encrypted volume) — skipping seed."
    fi

    # Seed Firestore after it's ready.
    # Non-fatal: a Firestore seed failure must not block ngrok or the other
    # emulators from starting.
    _seed_firestore "$FROM_GCP" || log_warn "Firestore seeding failed (will not block startup)."

    ngrok_tunnel_start

    echo ""
    log_info "------------------------------------------------------"
    log_info "All emulators are running."
    log_info ""
    log_info "  ✅ Secret Manager  : ${EMULATOR_HOST}"
    log_info "  ✅ Firestore        : ${FS_HOST}"
    log_info "  ✅ Pub/Sub          : ${PS_HOST}"
    log_info "  ✅ Encrypted volume : mounted"
    echo ""
    if [ -n "${SEEDED_SECRETS:-}" ]; then
        log_info "The app reads all config from local_config.json + emulators."
        log_info "No manual exports needed. Next: run the app."
        echo ""
        echo "  .venv/bin/python power_core/main.py"
    else
        log_info "Next: seed secrets (./local_dev.sh seed), then run the app."
    fi
    log_info "------------------------------------------------------"
}

cmd_stop() {
    ngrok_tunnel_stop

    log_info "Stopping pod '$POD_NAME' (all emulators)..."
    podman pod stop "$POD_NAME" 2>/dev/null || true
    podman pod rm -f "$POD_NAME" 2>/dev/null || true

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
    echo "export PUBSUB_EMULATOR_HOST=${PS_HOST}"
    echo "export GCP_PROJECT_ID=${PROJECT_ID}"
}

cmd_rotate_webhook() {
    # Update only DROpbox_WEBHOOK_PATH in the Secret Manager emulator.
    # All other secrets (Dropbox tokens, Strava keys, etc.) are left untouched.
    # Requires the emulator pod to be running.
    local emulator_base="http://${EMULATOR_HOST}"
    local secret_name="${APP_JSON_KEYS:-fullstack-app-json-keys}"

    # Health check
    if ! curl -sf "${emulator_base}/health" > /dev/null 2>&1; then
        log_error "Secret Manager emulator is not reachable at ${emulator_base}"
        log_error "  Start it first:  $0 start"
        return 1
    fi

    log_info "Rotating DROpbox_WEBHOOK_PATH (other secrets untouched)..."

    local new_path
    new_path=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
    log_info "New path: ${new_path}"

    # Fetch current secret, update the one key, POST new version — all via emulator API
    "$PYTHON_BIN" -c "
import json, urllib.request, secrets

base   = '${emulator_base}'
proj   = '${PROJECT_ID}'
secret = '${secret_name}'
new    = '${new_path}'

# fetch current version
resp = urllib.request.urlopen(f'{base}/v1/projects/{proj}/secrets/{secret}/versions/latest')
data = json.loads(json.loads(resp.read())['payload']['data'])

old = data.get('DROpbox_WEBHOOK_PATH', '<not set>')
data['DROpbox_WEBHOOK_PATH'] = new

# push new version
body = json.dumps({'payload': {'data': json.dumps(data)}}).encode()
req = urllib.request.Request(
    f'{base}/v1/projects/{proj}/secrets/{secret}:addVersion',
    data=body,
    headers={'Content-Type': 'application/json'},
)
result = json.loads(urllib.request.urlopen(req).read())

print(f'OLD: {old}')
print(f'NEW: {new}')
print(f'Version: {result[\"version\"]}')
print(f'Preserved: {len(data)} keys')
"

    echo ""
    log_info "Done. Paste this webhook URL into the Dropbox App console:"
    echo "    https://<ngrok-url>/${new_path}"
    echo ""
    log_info "Tip: run './ngrok.sh status' to see your current ngrok URL."
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
FROM_GCP=""
SEEDED_SECRETS=""
PROJECT_MODE="emulator"  # Default

# Parse arguments after the command name.
args=()
for arg in "$@"; do
    args+=("$arg")
done

for ((i = 1; i < ${#args[@]}; i++)); do
    case "${args[$i]}" in
        --from-gcp)
            FROM_GCP="1"
            ;;
        --project=*)
            PROJECT_MODE="${args[$i]#*=}"
            ;;
        --project)
            if ((i + 1 >= ${#args[@]})); then
                echo "ERROR: --project requires emulator, dev, or prod."
                exit 1
            fi
            PROJECT_MODE="${args[$((i + 1))]}"
            ((i++))
            ;;
    esac
done

# Validate project mode
if [[ "$PROJECT_MODE" != "emulator" && "$PROJECT_MODE" != "dev" && "$PROJECT_MODE" != "prod" ]]; then
    echo "🯀 ERROR: Invalid project mode '$PROJECT_MODE'. Use 'emulator', 'dev', or 'prod'."
    exit 1
fi

case "${1:-start}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    seed)   cmd_seed ;;
    env)    cmd_env ;;
    tunnel) ngrok_tunnel_start ;;
    rotate-webhook) cmd_rotate_webhook ;;
    *)
        echo "Usage: $0 {start [--project emulator|dev|prod] [--from-gcp]|stop|seed|env|tunnel|rotate-webhook}"
        exit 1
        ;;
esac
