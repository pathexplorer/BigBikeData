
from gcp_actions.client import get_env_and_cashed_it
from gcp_actions.secret_manager import SecretManagerClient
from power_core.project_env.config import BREVO_CREDENTIALS
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sm = SecretManagerClient(get_env_and_cashed_it("GCP_PROJECT_ID"))
access_email_dict = sm.get_secret_json(BREVO_CREDENTIALS)

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
    print("--- Attempting to send email via SMTP ---")
    try:
        # Use os.getenv for local config variables
        smtp_server_host = os.getenv("SMTP_SERVER")
        smtp_port_str = os.getenv("SMTP_PORT")
        sender_email = os.getenv("SENDER_EMAIL")
        # These are optional; if they exist, we'll try to log in.
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        if not all([smtp_server_host, smtp_port_str, sender_email]):
            raise EnvironmentError("Missing one or more required environment variables for SMTP: SMTP_SERVER, SMTP_PORT, SENDER_EMAIL")
        
        smtp_port = int(smtp_port_str)

        # --- NEW DIAGNOSTIC LOGGING ---
        print("-----------------------------------------")
        print(f"DIAGNOSTICS: About to connect to...")
        print(f"DIAGNOSTICS: Host: '{smtp_server_host}'")
        print(f"DIAGNOSTICS: Port: {smtp_port}")
        print("-----------------------------------------")
        # --- END DIAGNOSTIC LOGGING ---

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_server_host, smtp_port) as server:
            # If a user/password is provided, assume it's a real SMTP server
            if smtp_user and smtp_password:
                print("   -> Secure login required. Starting TLS...")
                server.starttls()  # Upgrade the connection to be secure
                server.login(smtp_user, smtp_password)
                print("   -> Login successful.")
            else:
                print("   -> No user/password found. Assuming local debug server.")

            server.send_message(msg)
        
        print(f"✅ Successfully sent email via SMTP for recipient: {recipient_email}")

    except Exception as e:
        print(f"❌ Failed to send email via SMTP: {e}")
        raise

def _send_email_brevo(recipient_email: str, subject: str, html_body: str):
    """Sends an email using the Brevo API, for production."""
    print("--- Attempting to send email via Brevo API ---")
    if not sib_api_v3_sdk:
        raise ImportError("The 'sib-api-v3-sdk' package is not installed. Cannot use Brevo sender.")
        
    try:
        # Use get_secret for production secrets
        api_key = access_email_dict.get("BREVO_API_KEY")
        sender_email = access_email_dict.get("SENDER_EMAIL")
        sender_name = access_email_dict.get("SENDER_NAME")

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
        print(f"✅ Successfully sent email to {recipient_email} via Brevo. Message ID: {api_response.message_id}")

    except ApiException as e:
        print(f"❌ Failed to send email via Brevo (API Error): {e.body}")
        raise
    except Exception as e:
        print(f"❌ An unexpected error occurred with Brevo sender: {e}")
        raise

def send_email(recipient_email: str, subject: str, html_body: str):
    """
    Sends an email using either a local SMTP server or the Brevo API,
    based on the EMAIL_MODE environment variable.
    """
    # It's safer to default to 'local' if the variable isn't set.
    email_mode = os.getenv("EMAIL_MODE", "local")

    if email_mode == 'brevo':
        _send_email_brevo(recipient_email, subject, html_body)
    else:
        if email_mode != 'local':
             print(f"⚠️ WARNING: Unknown EMAIL_MODE '{email_mode}'. Defaulting to local SMTP.")
        print("SMTP test mode")
        _send_email_smtp(recipient_email, subject, html_body)
