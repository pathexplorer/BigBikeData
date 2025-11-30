from flask import session, request, current_app
from flask_babel import Babel

def get_locale():
    """
    Selects language based on session or browser settings.
    :return: The language code, e.g. 'en' or 'uk'.
    """
    # Use current_app to access the app's config
    return session.get('language', request.accept_languages.best_match(current_app.config['LANGUAGES'].keys()))

# Create a Babel instance that can be imported by other modules
babel = Babel()

def init_babel(app):
    """Initializes Babel for the Flask app."""
    app.config['LANGUAGES'] = {'en': 'English', 'uk': 'Ukrainian'}
    babel.init_app(app, locale_selector=get_locale)
