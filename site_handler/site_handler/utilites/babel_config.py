"""Babel localization setup for the Flask app and the locale selector used to pick the active language."""
from flask import session, request, current_app
from flask_babel import Babel

def get_locale():
    """Return the active language: session override, else the best match from the browser's accepted languages."""
    # Use current_app to access the app's config
    return session.get('language', request.accept_languages.best_match(current_app.config['LANGUAGES'].keys()))

# Create a Babel instance that can be imported by other modules
babel = Babel()

def init_babel(app):
    """Initializes Babel for the Flask app."""
    app.config['LANGUAGES'] = {'en': 'English', 'uk': 'Ukrainian'}
    babel.init_app(app, locale_selector=get_locale)
