from flask import current_app, request, session, flash

def flash_and_log(msg, category=None):
    flash(msg, category)
    username = session["username"] if "username" in session else "N/A"
    url = request.referrer
    logmsg = f"[{category}] User: {username}, URL: {url} - {msg}"
    if category == "error":
        current_app.logger.warning(logmsg)
    else:
        current_app.logger.info(logmsg)

