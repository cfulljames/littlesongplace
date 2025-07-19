import json
import threading
import enum
from datetime import datetime, timedelta, timezone

import click
import pywebpush
from flask import Blueprint, current_app, g, request

from . import auth, datadir, db, songs

bp = Blueprint("push-notifications", __name__, url_prefix="/push-notifications")

push_threads = []

class SubscriptionSetting(enum.IntEnum):
    COMMENTS = 0x0001
    SONGS = 0x0002

@bp.post("/subscribe")
@auth.requires_login
def subscribe():
    if not request.json:
        # Request must contain valid subscription JSON
        abort(400)

    row = db.query(
            """
            INSERT INTO users_push_subscriptions (userid, subscription, settings)
            VALUES (?, ?, ?)
            RETURNING subid
            """,
            [g.userid, json.dumps(request.json), 0], expect_one=True)
    db.commit()

    current_app.logger.info(f"{g.username} registered push subscription")

    return {"status": "success", "subid": row["subid"]}

@bp.post("/update-subscription/<int:subid>")
@auth.requires_login
def update_subscription(subid):
    if not request.json:
        # Request must contain valid subscription JSON
        abort(400)

    row = db.query(
            """
            UPDATE users_push_subscriptions
            SET subscription = ?
            WHERE subid = ? AND userid = ?
            RETURNING subid
            """,
            [json.dumps(request.json), subid, g.userid], expect_one=True)
    db.commit()

    current_app.logger.info(f"{g.username} updated push subscription")

    return {"status": "success", "subid": row["subid"]}

@bp.get("/settings")
@auth.requires_login
def get_settings():
    subid = request.args["subid"]
    row = db.query(
            """
            SELECT settings FROM users_push_subscriptions
            WHERE subid = ? AND userid = ?
            """,
            [subid, g.userid], expect_one=True)

    comments = (row["settings"] & SubscriptionSetting.COMMENTS) > 0
    songs = (row["settings"] & SubscriptionSetting.SONGS) > 0

    return {"comments": comments, "songs": songs}

@bp.post("/update-settings")
@auth.requires_login
def update_settings():
    if not request.json:
        # Request must contain valid subscription JSON
        abort(400)

    bitfield = 0
    settings = request.json

    if ("subid" not in settings) or ("comments" not in settings) or ("songs" not in settings):
        abort(400)

    subid = settings["subid"]

    if settings["comments"]:
        bitfield |= SubscriptionSetting.COMMENTS
    if settings["songs"]:
        bitfield |= SubscriptionSetting.SONGS

    db.query(
            """
            UPDATE users_push_subscriptions
            SET settings = ?
            WHERE subid = ? AND userid = ?
            """,
            [bitfield, subid, g.userid])
    db.commit()

    current_app.logger.info(f"{g.username} updated push subscription settings: ({subid}) {bitfield:04x}")

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
            subs.append((r["subid"], r["settings"], json.loads(s)))
        except json.decoder.JSONDecodeError:
            current_app.logger.error(f"Invalid subscription: {s}")
    return subs

def notify_all(title, body, url, setting, _except=None):
    # Notify all users (who have notifications enabled)
    rows = db.query("SELECT * FROM users")
    userids = [r["userid"] for r in rows]
    if _except in userids:
        userids.remove(_except)
    notify(userids, title, body, url, setting)

def notify(userids, title, body, url, setting):
    # Send push notifications in background thread (could take a while)
    thread = threading.Thread(
            target=_do_push,
            args=(current_app._get_current_object(), userids, title, body, url, setting))
    push_threads.append(thread)
    thread.start()

def wait_all():
    push_copy = push_threads[:]
    for thread in push_copy:
        thread.join()

def _do_push(app, userids, title, body, url, setting):
    data = {"title": title, "body": body, "url": url}
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
            for subid, sub_settings, sub in subs:
                if not (sub_settings & setting):
                    continue  # This setting is disabled for this subscription
                try:
                    if private_key:
                        pywebpush.webpush(sub, data_str, vapid_private_key=private_key, vapid_claims=claims.copy())
                    else:
                        pywebpush.webpush(sub, data_str)

                    sent_notifications += 1
                except pywebpush.WebPushException as ex:
                    # Failed to send notification, delete this subscription
                    app.logger.warning(f"Deleting dead push subscription: {subid} - {ex}")
                    db.query("DELETE FROM users_push_subscriptions WHERE subid = ?", [subid])
                    db.commit()

        if sent_notifications > 0:
            app.logger.info(f"Pushed {sent_notifications} notifications")

    push_threads.remove(threading.current_thread())

@click.command("notify-new-songs")
def notify_new_songs_cmd():
    """Notify subscribed users that new songs have been uploaded"""
    with current_app.app_context():
        one_day = timedelta(days=1)
        yesterday = (datetime.now(timezone.utc) - one_day).isoformat()
        new_songs = songs.get_uploaded_since(yesterday)
        unique_users = sorted(set(s.username for s in new_songs))

        title = None
        _except = None
        if len(new_songs) == 1:
            title = f"New song from {unique_users[0]}"
            _except = new_songs[0].userid
        elif len(new_songs) > 1:
            title = f"New songs from {', '.join(unique_users)}"

        if title:
            notify_all(
                    title,
                    body=None,
                    url="/",
                    setting=SubscriptionSetting.SONGS,
                    _except=_except)

def init_app(app):
    app.cli.add_command(notify_new_songs_cmd)
