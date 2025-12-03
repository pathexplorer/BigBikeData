from flask import Blueprint, session, redirect, url_for, request, current_app
bp4 = Blueprint('language', __name__, url_prefix='/language')


@bp4.route('/<lang>')
def set_language(lang=None):

    if lang in current_app.config['LANGUAGES']:
        session['language'] = lang
        session.modified = True  # Explicitly mark the session as modified

    # Always redirect to the main index page. This is more robust behind a proxy
    # than relying on request.referrer.
    target = url_for('frontend.index', _external=False)

    response = redirect(target)
    current_app.session_interface.save_session(current_app, session, response)
    return response

# @bp4.route('/test')
# def test_language():
#     current_app.logger.info("--- /language/test route hit ---")
#     return {"status": "ok", "message": "Language route reachable"}

