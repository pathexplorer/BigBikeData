
from power_core.project_env.config import SMTP_USER, SMTP_PASSWORD, SMTP_SERVER, SMTP_PORT, SMTP_SENDER, BREVO_API_KEY, SENDER_NAME, SENDER_EMAIL, EMAIL_MODE
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import logging
logger = logging.getLogger(__name__)

# Try to import Brevo, but don't fail if it's not installed
try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
except ImportError:
    sib_api_v3_sdk = None
    ApiException = None


def _send_email_smtp(recipient_email: str, subject: str, html_body: str):
    """
    Sends an email using a standard SMTP server.
    It supports both the simple local debugger and real SMTP servers like Gmail.
    """
    logger.debug("Attempting to send email via SMTP")
    try:
        smtp_server_host = SMTP_SERVER
        smtp_port_str = SMTP_PORT
        smtp_sender = SMTP_SENDER
        # These are optional; if they exist, we'll try to log in.
        smtp_user = SMTP_USER
        smtp_password = SMTP_PASSWORD

        if not all([smtp_server_host, smtp_port_str, smtp_sender]):
            raise EnvironmentError("Missing one or more required environment variables for SMTP: SMTP_SERVER, SMTP_PORT, SMTP_SENDER")
        
        smtp_port = int(smtp_port_str)

        # --- NEW DIAGNOSTIC LOGGING ---
        logger.debug(f"About to connect to...")
        logger.debug(f"Host: '{smtp_server_host}'")
        logger.debug(f"Port: {smtp_port}")
        # --- END DIAGNOSTIC LOGGING ---

        msg = MIMEMultipart()
        msg["From"] = smtp_sender
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_server_host, smtp_port) as server:
            # If a user/password is provided, assume it's a real SMTP server
            if smtp_user and smtp_password:
                logger.debug("   -> Secure login required. Starting TLS...")
                server.starttls()  # Upgrade the connection to be secure
                server.login(smtp_user, smtp_password)
                logger.info("   -> Login at SMTP server successful.")
            else:
                logger.warning("   -> No user/password found. Assuming local debug server.")

            server.send_message(msg)
        
        logger.info(f"✅ Successfully sent email via SMTP for recipient: {recipient_email}")

    except Exception as e:
        logger.error(f"❌ Failed to send email via SMTP: {e}")
        raise

def _send_email_brevo(recipient_email: str, subject: str, html_body: str):
    """Sends an email using the Brevo API, for production."""
    logger.debug("Attempting to send email via Brevo API")
    if not sib_api_v3_sdk:
        raise ImportError("The 'sib-api-v3-sdk' package is not installed. Cannot use Brevo sender.")
        
    try:
        # Use get_secret for production secrets
        api_key = BREVO_API_KEY
        sender_email = SENDER_EMAIL
        sender_name = SENDER_NAME

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = api_key
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

        # --- Create the Email ---
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": recipient_email}],
            sender={"name": sender_name, "email": sender_email},
            subject=subject,
            html_content=html_body
        )

        api_response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"✅ Successfully sent email to: {recipient_email} via Brevo.")
        logger.debug(f"Message ID: {api_response.message_id}")

    except ApiException as e:
        logger.error(f"❌ Failed to send email via Brevo (API Error): {e.body}")
        raise
    except Exception as e:
        logger.error(f"❌ An unexpected error occurred with Brevo sender: {e}")
        raise

def send_email(recipient_email: str, subject: str, html_body: str):
    """
    Sends an email using either a local SMTP server or the Brevo API,
    based on the EMAIL_MODE environment variable.
    """
    if EMAIL_MODE == 'brevo':
        _send_email_brevo(recipient_email, subject, html_body)
    else:
        if EMAIL_MODE != 'local':
             logger.warning(f"Unknown EMAIL_MODE '{EMAIL_MODE}'. Defaulting to local SMTP.")
        logger.warning("SMTP test mode")
        _send_email_smtp(recipient_email, subject, html_body)
