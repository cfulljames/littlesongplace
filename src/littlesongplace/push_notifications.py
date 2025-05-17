import json
import threading

import pywebpush
from flask import Blueprint, current_app, g, request

from . import auth, db

bp = Blueprint("push-notifications", __name__, url_prefix="/push-notifications")

@bp.post("/subscribe")
@auth.requires_login
def subscribe():
    if not request.json:
        # Request must contain valid subscription JSON
        abort(400)

    db.query(
            """
            INSERT INTO users_push_subscriptions (userid, subscription)
            VALUES (?, ?)
            """,
            [g.userid, json.dumps(request.json)])
    db.commit()

    current_app.logger.info(f"{g.username} registered push subscription")

    return {"status": "success"}

def get_user_subscriptions(userid):
    rows = db.query(
            """
            SELECT * FROM users_push_subscriptions
            WHERE userid = ?
            """,
            [userid])
    str_subs = (r["subscription"] for r in rows)
    subs = []
    for s in str_subs:
        try:
            subs.append(json.loads(s))
        except json.decoder.JSONDecodeError:
            current_app.logger.error(f"Invalid subscription: {s}")
    return subs

def notify_all(title, body, _except=None):
    # Notify all users (who have notifications enabled)
    rows = db.query("SELECT * FROM users")
    userids = [r["userid"] for r in rows]
    if _except in userids:
        userids.remove(_except)
    notify(userids, title, body)

def notify(userids, title, body):
    # Send push notifications in background thread (could take a while)
    thread = threading.Thread(
            target=_do_push,
            args=(current_app._get_current_object(), userids, title, body))
    thread.start()

def _do_push(app, userids, title, body):
    data = {"title": title, "body": body}
    data_str = json.dumps(data)
    for userid in userids:
        with app.app_context():
            subs = get_user_subscriptions(userid)
            for sub in subs:
                try:
                    # TODO: Use VAPID keys
                    pywebpush.webpush(sub, data_str)
                except pywebpush.WebPushException as ex:
                    current_app.logger.error(f"Failed to send push: {ex}")

