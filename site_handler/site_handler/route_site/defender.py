from flask import Blueprint, request, abort
import os
import logging
from site_handler.utilites.site_config import ALLOWED_DOMAINS

logger = logging.getLogger(__name__)

bp9 = Blueprint('defender', __name__,)


# Convert the comma-separated string into a set for fast, case-insensitive lookup
ALLOWED_HOSTS = set(domain.strip().lower() for domain in ALLOWED_DOMAINS.split(','))

logger.debug(f"Loaded ALLOWED_HOSTS: {ALLOWED_HOSTS}")


def extract_hostname(host_header: str) -> str:
    """
    Extract hostname from Host header, removing port if present.
    Examples:
        'example.com:443' -> 'example.com'
        'example.com' -> 'example.com'
        '127.0.0.1:5000' -> '127.0.0.1'
    """
    if not host_header:
        return ''
    return host_header.split(':')[0].lower()


@bp9.before_app_request  # Use before_app_request to run before ALL routes
def restrict_direct_access():
    """
    Security Middleware:
    Blocks direct access to the 'run.app' URL and enforces the ALLOWED_HOSTS list.
    """
    # 1. Get the Host header (The domain the user typed/was forwarded)
    host_raw = request.headers.get('Host', '')
    host = extract_hostname(host_raw)

    # 2. Check X-Forwarded-Host (often set by proxies like Firebase Hosting)
    forwarded_host_raw = request.headers.get('X-Forwarded-Host', '')
    forwarded_host = extract_hostname(forwarded_host_raw)

    # RULE 1: Immediate rejection of run.app (kills bot cold starts fast)
    # Checks both headers for the known bad pattern.
    if 'run.app' in host or 'run.app' in forwarded_host:
        logger.warning(f"BLOCKED BOT (RUN.APP): Host={host_raw}, Fwd-Host={forwarded_host_raw}")
        abort(403, description="Direct Cloud Run access forbidden.")

    # RULE 2: Strict Allowlist Enforcement
    # A request is valid if EITHER the Host or the X-Forwarded-Host matches an allowed domain.
    valid_request = host in ALLOWED_HOSTS or forwarded_host in ALLOWED_HOSTS

    if not valid_request:
        logger.warning(f"BLOCKED UNKNOWN HOST: Host={host_raw}, Fwd-Host={forwarded_host_raw}, Allowed: {ALLOWED_HOSTS}")
        # Blocks traffic from any other domain (including random subdomains or IP addresses)
        abort(403, description="Invalid or unauthorized Host header.")
    
    # Log successful access (optional but useful for debugging)
    logger.debug(f"✅ ALLOWED: Host={host}, Fwd-Host={forwarded_host}")