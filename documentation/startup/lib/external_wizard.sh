#!/usr/bin/env bash

# External Services Wizard - interactive guided collection of per-environment
# credentials for Dropbox, Strava, Brevo/SMTP, site hosting and ngrok.
# Walks the user through external_services_setup.md, validates that values were
# obtained, and persists them in a gpg-encrypted state file (never plaintext).
# The uploaded payloads mirror SECRET_CONFIG_MAP in gcp_actions emulators.

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
# Key registry: value becomes available under the same-name environment variable
# after the wizard, so configure_runtime.sh picks it up on --apply.
WIZARD_ORDER=()
declare -A WIZARD_DESC=()     # human readable label
declare -A WIZARD_SECRET=()   # "1" -> mask + read with -s
declare -A WIZARD_DEST=()     # destination: dropbox-secrets | fullstack | cloudrun | local
declare -A WIZARD_VAL=()      # collected value
WIZ_GPG_PASS=""
WIZ_STATE_FILE=""

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
_wiz_register() {
    local key="$1" desc="$2" secret="$3" dest="$4"
    WIZARD_ORDER+=("$key")
    WIZARD_DESC["$key"]="$desc"
    WIZARD_SECRET["$key"]="$secret"
    WIZARD_DEST["$key"]="$dest"
}

_wiz_set() {
    WIZARD_VAL["$1"]="$2"
    export "$1=$2"
}

_wiz_masked() {
    local v="${1:-}"
    if [[ -z "$v" ]]; then
        echo "(empty)"
    elif (( ${#v} <= 4 )); then
        echo "****"
    else
        echo "${v:0:3}****"
    fi
}

wizard_yes_no() {
    # $1 = question; returns 0 on Y, 1 on N (default N unless second arg "default=y")
    local default="${2:-n}"
    local yn=""
    while true; do
        read -r -p "$1 [y/N]: " yn
        case "${yn,,}" in
            y|yes) return 0 ;;
            "" ) if [[ "$default" == "y" ]]; then return 0; else return 1; fi ;;
            n|no) return 1 ;;
        esac
    done
}

wizard_section() {
    echo ""
    echo "──────────────────────────────────────────────────────────────"
    echo "  $1"
    echo "──────────────────────────────────────────────────────────────"
}

# ---------------------------------------------------------------------------
# Interactive prompt for one variable (prefilled from encrypted state)
# ---------------------------------------------------------------------------
wizard_prompt() {
    local key="$1"
    local desc="${WIZARD_DESC[$key]}"
    local is_secret="${WIZARD_SECRET[$key]}"
    local cur="${WIZARD_VAL[$key]:-}"

    if [[ -n "$cur" ]]; then
        if [[ "$is_secret" == "1" ]]; then
            echo "  ${key} (current: $(_wiz_masked "$cur")) — Enter to keep, or type a new value."
        else
            echo "  ${key} (current: $cur) — Enter to keep, or type a new value."
        fi
    else
        echo "  ${key} — $desc"
    fi

    local new_val=""
    if [[ "$is_secret" == "1" ]]; then
        read -r -s -p "    ${key}: " new_val || wizard_abort
        echo ""
    else
        read -r -p "    ${key}: " new_val || wizard_abort
    fi

    if [[ -n "$new_val" ]]; then
        _wiz_set "$key" "$new_val"
    elif [[ -z "$cur" ]]; then
        echo "  (left empty)"
    fi
}

# ---------------------------------------------------------------------------
# gpg state persistence (secrets never stored as plaintext on disk)
# ---------------------------------------------------------------------------
wizard_state_path() {
    echo "${SCRIPT_DIR:?SCRIPT_DIR not set}/.external_services.${ENV_MODE:?ENV_MODE not set}.gpg"
}

_wiz_gpg_get_pass() {
    if [[ -n "$WIZ_GPG_PASS" ]]; then
        return 0
    fi
    if [[ ! -t 0 ]]; then
        echo "  No passphrase available (not a terminal). Cannot read/save the encrypted state." >&2
        return 1
    fi
    read -r -s -p "Passphrase for the encrypted external-services state file: " WIZ_GPG_PASS
    echo ""
    if [[ -z "$WIZ_GPG_PASS" ]]; then
        echo "  A passphrase is required." >&2
        return 1
    fi
}

load_wizard_state() {
    WIZ_STATE_FILE="$(wizard_state_path)"
    if [[ ! -f "$WIZ_STATE_FILE" ]]; then
        return 0
    fi
    if ! _wiz_gpg_get_pass; then
        return 1
    fi
    local tmp
    tmp="$(mktemp)"
    if ! printf '%s' "$WIZ_GPG_PASS" | gpg --quiet --batch --yes \
        --pinentry-mode loopback --passphrase-fd 0 -d "$WIZ_STATE_FILE" > "$tmp" 2>/dev/null; then
        echo "  Failed to decrypt ${WIZ_STATE_FILE}. Wrong passphrase?" >&2
        rm -f "$tmp"
        return 1
    fi
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" == "#"* ]] && continue
        _wiz_set "$key" "$value"
    done < "$tmp"
    rm -f "$tmp"
    echo "  Loaded previously saved external-services values from ${WIZ_STATE_FILE}"
}

save_wizard_state() {
    WIZ_STATE_FILE="$(wizard_state_path)"
    if [[ -z "$WIZ_GPG_PASS" ]]; then
        if ! _wiz_gpg_get_pass; then
            return 1
        fi
        read -r -s -p "Repeat passphrase to confirm: " WIZ_CONFIRM
        echo ""
        if [[ "$WIZ_CONFIRM" != "$WIZ_GPG_PASS" ]]; then
            echo "  Passphrases do not match. Not saving state." >&2
            return 1
        fi
    fi
    local tmp
    tmp="$(mktemp)"
    for key in "${WIZARD_ORDER[@]}"; do
        local val="${WIZARD_VAL[$key]:-}"
        [[ -n "$val" ]] && printf '%s=%s\n' "$key" "$val" >> "$tmp"
    done
    printf '%s' "$WIZ_GPG_PASS" | gpg --quiet --batch --yes \
        --pinentry-mode loopback --passphrase-fd 0 \
        --symmetric --cipher-algo AES256 -o "$WIZ_STATE_FILE" "$tmp" 2>/dev/null
    rm -f "$tmp"
    chmod 600 "$WIZ_STATE_FILE" 2>/dev/null || true
    echo "  Encrypted external-services state saved to ${WIZ_STATE_FILE}"
    export WIZ_STATE_FILE
}

wizard_require() {
    # Always prompt once (allows keep/change of a previous value), then keep
    # asking until a value is provided.
    local key="$1"
    wizard_prompt "$key"
    while [[ -z "${WIZARD_VAL[$key]:-}" ]]; do
        wizard_prompt "$key"
    done
}

# ---------------------------------------------------------------------------
# Graceful interruption: persist whatever the user already entered so a later
# run resumes from exactly where the wizard was stopped.
# Idempotent — safe to call from a signal trap AND from a failed `read`.
# ---------------------------------------------------------------------------
WIZ_ABORTING=0

wizard_abort() {
    if [[ "$WIZ_ABORTING" == "1" ]]; then
        exit 130
    fi
    WIZ_ABORTING=1
    trap - INT TERM
    echo ""
    echo "  ⏸  Interrupted. Saving external-services progress..."
    local saved=1
    if save_wizard_state 2>/dev/null && [[ -f "$(wizard_state_path)" ]]; then
        saved=0
    fi
    if [[ "$saved" == 0 ]]; then
        echo "  ✅ Progress saved. Re-run ./main.sh ${ENV_MODE} to continue —"
        echo "      previously entered values will be pre-filled."
    else
        echo "  ⚠️  Progress could not be saved (no passphrase available)."
        echo "      Values already entered will be lost on exit."
    fi
    exit 130
}

# Install during the wizard phase only (main.sh).
wizard_install_signal_trap() {
    trap 'wizard_abort' INT TERM
}

# ---------------------------------------------------------------------------
# Wizard: one guided section per external service (external_services_setup.md)
# ---------------------------------------------------------------------------
wizard_dropbox() {
    wizard_section "1. Dropbox  (external_services_setup.md §1)"
    echo "  Create a Scoped App with FULL DROPBOX access (scopes: files.metadata.read/write,"
    echo "  files.content.read/write) inside the App Console."
    echo "  Get a refresh token via the console (expires in 10 days — refresh token is permanent)."
    echo "  Configure the webhook later to: {CLOUD_RUN_URL}/<DROpbox_WEBHOOK_PATH>."
    echo ""
    wizard_require DROPBOX_APP_KEY
    wizard_require DROPBOX_APP_SECRET
    wizard_require DROPBOX_REFRESH_TOKEN
    if [[ -z "${WIZARD_VAL[DROPBOX_WATCHED_FOLDER]:-}" ]]; then
        _wiz_set DROPBOX_WATCHED_FOLDER "/apps/activities"
    fi
    echo "  Note: the Wahoo connection must create exactly ONE watched folder;"
    echo "  its path overrides DROPBOX_WATCHED_FOLDER if it differs."
}

wizard_strava() {
    wizard_section "2. Strava  (external_services_setup.md §2)"
    echo "  The Strava app is shared across environments; credentials are stored in"
    echo "  the combined dropbox-secrets secret and are needed whenever the upload"
    echo "  stage runs (STRAVA_UPLOAD toggle). They are collected in BOTH environments"
    echo "  — in dev they are optional, in prod they are required."
    echo ""
    if [[ "$ENV_MODE" != "prod" ]]; then
        _wiz_set STRAVA_UPLOAD "disable"
        echo "  STRAVA_UPLOAD = disable (dev hard rule; the upload stage never runs)."
    else
        wizard_prompt STRAVA_UPLOAD
    fi
    if [[ "${WIZARD_VAL[STRAVA_UPLOAD]:-}" != "disable" ]]; then
        wizard_require STRAVA_CLIENT_ID
        wizard_require STRAVA_CLIENT_SECRET
    else
        echo "  (dev) Leave empty to skip — or enter the real values if you want them"
        echo "        available later when the upload stage is enabled."
        wizard_prompt STRAVA_CLIENT_ID
        wizard_prompt STRAVA_CLIENT_SECRET
    fi
    echo "  STRAVA_REFRESH_TOKEN — optional now; obtain it later via"
    echo "  power_core/power_core/strava/get_refresh_token.py"
    wizard_prompt STRAVA_REFRESH_TOKEN
}

wizard_email() {
    wizard_section "3. Email — Brevo (primary) / SMTP fallback  (external_services_setup.md §3)"
    echo "  EMAIL_MODE: 'brevo' (API key + per-env sender) or 'local' (SMTP settings)."
    if [[ -z "${WIZARD_VAL[EMAIL_MODE]:-}" ]]; then
        _wiz_set EMAIL_MODE "brevo"
    fi
    wizard_prompt EMAIL_MODE
    if [[ "${WIZARD_VAL[EMAIL_MODE]}" == "brevo" ]]; then
        wizard_require SENDER_EMAIL
        wizard_prompt SENDER_NAME
        wizard_prompt BREVO_API_KEY
    else
        echo "  Provide the SMTP relay settings below (all optional unless you use the pipeline's email stage)."
        for key in SMTP_SERVER SMTP_PORT SMTP_SENDER SMTP_USER SMTP_PASSWORD; do
            wizard_prompt "$key"
        done
    fi
}

wizard_hosting() {
    wizard_section "4. Site hosting  (external_services_setup.md §4)"
    echo ""
    echo "  FRONTEND_BASE_URL — the public URL users will open the site at."
    echo "    This is YOUR domain decision (e.g. https://test.offteleport.cloud)."
    echo ""
    echo "  ALLOWED_DOMAINS — a SECURITY allow-list. The site_handler Cloud Run"
    echo "    service rejects any request whose Host header is NOT in this list"
    echo "    (documentation: site_handler/site_handler/route_site/defender.py)."
    echo "    List every domain that may reach the site — the frontend domain"
    echo "    above, and for dev also the Firebase Preview Channel URL and localhost:"
    echo "      prod:  app.example.com"
    echo "      dev:   sometest.offteleport.cloud,bigbikedata--dev-app.web.app,localhost"
    echo "    (comma-separated, no https://, just hostnames.)"
    echo ""
    wizard_require FRONTEND_BASE_URL

    # Auto-suggest the allowlist from the base URL so the user only confirms it.
    local auto_domains=""
    if [[ -z "${WIZARD_VAL[ALLOWED_DOMAINS]:-}" ]]; then
        auto_domains="${FRONTEND_BASE_URL#https://}"
        auto_domains="${auto_domains#http://}"
        auto_domains="${auto_domains%%/*}"
        if [[ "$ENV_MODE" == "dev" ]]; then
            auto_domains="${auto_domains},localhost"
        fi
        _wiz_set ALLOWED_DOMAINS "$auto_domains"
        echo "  Suggestion (based on FRONTEND_BASE_URL) — press Enter to accept:"
    fi
    wizard_prompt ALLOWED_DOMAINS
    echo ""
    echo "  Example dev value to see in the summary: ${auto_domains}"
}

wizard_ngrok() {
    wizard_section "5. ngrok (local webhook testing only)  (external_services_setup.md §5)"
    echo "  Token is kept LOCALLY only (KDE Wallet or NGROK_AUTHTOKEN); never stored in the cloud."
    wizard_prompt NGROK_AUTHTOKEN
}

# Full interactive walkthrough
run_external_wizard() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║      Step 1/3 — External services setup (guided wizard)     ${ENV_MODE}"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo "  Reference: documentation/external_services_setup.md"
    echo "  Values are collected interactively and stored ENCRYPTED (gpg) —"
    echo "  they are never written as plaintext to disk."

    load_wizard_state || return 1

    # --- register the variable registry for this environment ---
    _wiz_register DROPBOX_APP_KEY "App Key from Dropbox dev console" 1 "dropbox-secrets"
    _wiz_register DROPBOX_APP_SECRET "App Secret from Dropbox dev console" 1 "dropbox-secrets"
    _wiz_register DROPBOX_REFRESH_TOKEN "Dropbox OAuth2 refresh token" 1 "dropbox-secrets"
    _wiz_register DROPBOX_WATCHED_FOLDER "Watched folder path (default /apps/activities)" 0 "cloudrun"
    _wiz_register STRAVA_UPLOAD "Enable/disable Strava upload stage" 0 "fullstack"
    _wiz_register STRAVA_CLIENT_ID "Strava API client id" 1 "dropbox-secrets"
    _wiz_register STRAVA_CLIENT_SECRET "Strava API client secret" 1 "dropbox-secrets"
    _wiz_register STRAVA_REFRESH_TOKEN "Strava OAuth refresh token" 1 "dropbox-secrets"
    _wiz_register EMAIL_MODE "Email backend switch: brevo | local" 0 "fullstack"
    _wiz_register BREVO_API_KEY "Brevo API key" 1 "fullstack"
    _wiz_register SENDER_EMAIL "Per-environment from-address" 0 "fullstack"
    _wiz_register SENDER_NAME "From display name" 0 "fullstack"
    _wiz_register SMTP_SERVER "SMTP host" 0 "fullstack"
    _wiz_register SMTP_PORT "SMTP port" 0 "fullstack"
    _wiz_register SMTP_SENDER "SMTP from-address" 0 "fullstack"
    _wiz_register SMTP_USER "SMTP auth user" 0 "fullstack"
    _wiz_register SMTP_PASSWORD "SMTP auth password" 1 "fullstack"
    _wiz_register FRONTEND_BASE_URL "Public frontend URL (per env)" 0 "fullstack"
    _wiz_register ALLOWED_DOMAINS "Comma-separated domain allowlist" 0 "cloudrun"
    _wiz_register NGROK_AUTHTOKEN "ngrok authtoken (local only)" 1 "local"

    wizard_dropbox
    wizard_strava
    wizard_email
    wizard_hosting
    wizard_ngrok

    echo ""
    echo "  Wizard finished."
}

# ---------------------------------------------------------------------------
# Summary table: "you configured external services, we have these keys"
# ---------------------------------------------------------------------------
show_external_summary() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║   External services configured — variables & keys available  ${ENV_MODE}"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    printf "  %-28s %-22s %s\n" "VARIABLE" "DESTINATION" "VALUE"
    printf "  %-28s %-22s %s\n" "---------------------------" "----------------------" "----------"
    for key in "${WIZARD_ORDER[@]}"; do
        local val="${WIZARD_VAL[$key]:-}"
        local shown="$val"
        if [[ "${WIZARD_SECRET[$key]}" == "1" ]]; then
            shown="$(_wiz_masked "$val")"
        fi
        printf "  %-28s %-22s %s\n" "$key" "${WIZARD_DEST[$key]}" "$shown"
    done
    echo ""
    echo "  Mandatory values are enforced by the wizard. Missing values below"
    echo "  mean an external credential still needs to be obtained manually."
    local missing=0
    for key in "${WIZARD_ORDER[@]}"; do
        if [[ -z "${WIZARD_VAL[$key]:-}" && "${WIZARD_SECRET[$key]}" == "1" ]]; then
            [[ "$missing" == 0 ]] && printf "  Missing: %s" "$key" || printf ", %s" "$key"
            missing=1
        fi
    done
    [[ "$missing" == 0 ]] && echo "  All credential fields collected." || echo ""
}

# ---------------------------------------------------------------------------
# Review step: numbered menu to re-enter any single value WITHOUT walking the
# whole wizard again. Called after the summary table.
# ---------------------------------------------------------------------------
_wiz_show_review_menu() {
    echo ""
    echo "  ——— Review / change values ———"
    local n=1
    for key in "${WIZARD_ORDER[@]}"; do
        local val="${WIZARD_VAL[$key]:-}"
        local shown="$val"
        if [[ "${WIZARD_SECRET[$key]}" == "1" ]]; then
            shown="$(_wiz_masked "$val")"
        fi
        printf "   %2d) %-24s %s\n" "$n" "$key" "$shown"
        n=$((n + 1))
    done
    echo ""
}

wizard_review_loop() {
    local choice=""
    while true; do
        _wiz_show_review_menu
        read -r -p "  Enter the number to change a value, or press Enter to keep all: " choice || wizard_abort
        if [[ -z "$choice" ]]; then
            return 0
        fi
        if [[ "$choice" =~ ^[0-9]+$ ]]; then
            local idx=$((choice - 1))
            if (( idx >= 0 && idx < ${#WIZARD_ORDER[@]} )); then
                local key="${WIZARD_ORDER[$idx]}"
                echo ""
                echo "  Re-enter ${key} (Enter keeps the current value):"
                wizard_prompt "$key"
                echo ""
                continue
            fi
        fi
        echo "  Invalid choice: $choice (pick a number, or press Enter to finish)."
    done
}

# ---------------------------------------------------------------------------
# Upload collected external values into Secret Manager (merging existing)
# ---------------------------------------------------------------------------
_upload_secret_payload() {
    # $1 project, $2 secret id, $3 json file, remaining = app secret keys
    local project="$1" secret_id="$2" payload="$3"
    shift 3
    python3 - "$project" "$secret_id" "$payload" "$@" <<'PY'
import json, os, subprocess, sys

project, secret_id, payload_path = sys.argv[1], sys.argv[2], sys.argv[3]
keys = sys.argv[4:]

# Start from the existing latest secret version, if readable, to avoid
# clobbering values provided in an earlier run. Skipped in dry-run.
data = {}
if os.environ.get("DRY_RUN") != "true":
    try:
        existing = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             "--secret", secret_id, "--project", project],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
        data = json.loads(existing)
    except Exception:
        pass

for k in keys:
    v = os.environ.get(k)
    if v:
        data[k] = v

with open(payload_path, "w") as f:
    json.dump(data, f, indent=2, sort_keys=True)
print(f"    {secret_id} <- {sorted(set(k for k in keys if os.environ.get(k)))}")
PY
}

upload_external_secrets() {
    local project="${GCP_PROJECT_ID:?GCP_PROJECT_ID required}"
    local tmpdir
    tmpdir="$(mktemp -d)"
    # Safe cleanup: embed the concrete path so the EXIT trap still works after
    # this function returns (the local would otherwise be unbound under set -u).
    trap "rm -f -- '$tmpdir'/*.json; rmdir -- '$tmpdir' 2>/dev/null || true" EXIT

    SEC_DROPBOX="${SEC_DROPBOX:?SEC_DROPBOX not set — source names.env first}"
    SEC_FULLSTACK_JSON_KEYS="${SEC_FULLSTACK_JSON_KEYS:?SEC_FULLSTACK_JSON_KEYS not set — source names.env first}"

    local dropbox_json="$tmpdir/dropbox-secrets.json"
    local fullstack_json="$tmpdir/fullstack-app-json-keys.json"

    echo ""
    echo "  Uploading external-service values into Secret Manager (project: $project)"

    _upload_secret_payload "$project" "$SEC_DROPBOX" "$dropbox_json" \
        DROPBOX_APP_KEY DROPBOX_APP_SECRET DROPBOX_REFRESH_TOKEN \
        STRAVA_CLIENT_ID STRAVA_CLIENT_SECRET STRAVA_REFRESH_TOKEN

    _upload_secret_payload "$project" "$SEC_FULLSTACK_JSON_KEYS" "$fullstack_json" \
        EMAIL_MODE BREVO_API_KEY SENDER_EMAIL SENDER_NAME \
        SMTP_SERVER SMTP_PORT SMTP_SENDER SMTP_USER SMTP_PASSWORD \
        STRAVA_UPLOAD FRONTEND_BASE_URL

    # actual upload (guarded by DRY_RUN)
    for pair in "$SEC_DROPBOX:$dropbox_json" "$SEC_FULLSTACK_JSON_KEYS:$fullstack_json"; do
        local secret_id="${pair%%:*}"
        local jsonf="${pair#*:}"
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            echo "  🔍 [DRY-RUN] gcloud secrets versions add ${secret_id} --data-file=${jsonf} --project=${project}"
        else
            gcloud secrets versions add "$secret_id" --data-file="$jsonf" --project="$project" >/dev/null
            echo "  ✅ ${secret_id} updated (new version)."
        fi
    done
}