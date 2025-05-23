import json
import threading

import pywebpush
from flask import Blueprint, current_app, g, request

from . import auth, datadir, db

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
    # print([dict(r) for r in rows])
    # str_subs = (r["subscription"] for r in rows)
    subs = []
    for r in rows:
        s = r["subscription"]
        try:
            subs.append((r["subid"], json.loads(s)))
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

    private_key_path = datadir.get_vapid_private_key_path()
    claims = {"sub": "mailto:littlesongplace@gmail.com"}
    private_key = None
    if private_key_path.exists():
        with open(private_key_path, "r") as private_key_file:
            private_key = private_key_file.read().strip()

    sent_notifications = 0
    with app.app_context():
        for userid in userids:
            subs = get_user_subscriptions(userid)
            for subid, sub in subs:
                try:
                    if private_key:
                        pywebpush.webpush(sub, data_str, vapid_private_key=private_key, vapid_claims=claims)
                    else:
                        pywebpush.webpush(sub, data_str)

                    sent_notifications += 1
                except pywebpush.WebPushException as ex:
                    if ex.response.status_code == 410:  # Subscription deleted
                        app.logger.warning(f"Deleting dead push subscription: {subid}")
                        db.query("DELETE FROM users_push_subscriptions WHERE subid = ?", [subid])
                        db.commit()
                    else:
                        app.logger.error(f"Failed to send push: {ex}")

        if sent_notifications > 0:
            app.logger.info(f"Pushed {sent_notifications} notifications")

