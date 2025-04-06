import base64
import enum
import logging
import os
import random
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click
from flask import Flask, render_template, request, redirect, g, session, abort, \
        send_from_directory, flash, get_flashed_messages
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import auth, colors, comments, datadir, db, profiles, songs, users
from .logutils import flash_and_log
from .sanitize import sanitize_user_text

################################################################################
# Logging
################################################################################

handler = RotatingFileHandler(datadir.get_app_log_path(), maxBytes=1_000_000, backupCount=10)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))

root_logger = logging.getLogger()
root_logger.addHandler(handler)

################################################################################
# Routes
################################################################################

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"] if "SECRET_KEY" in os.environ else "dev"
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024 * 1024
app.register_blueprint(auth.bp)
app.register_blueprint(comments.bp)
app.register_blueprint(profiles.bp)
app.register_blueprint(songs.bp)
db.init_app(app)

if "DATA_DIR" in os.environ:
    # Running on server behind proxy
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )
    app.logger.setLevel(logging.INFO)

@app.route("/")
def index():
    all_users = db.query("select * from users order by username asc")
    all_users = [dict(row) for row in all_users]
    for user in all_users:
        user["has_pfp"] = users.user_has_pfp(user["userid"])
        for key, value in users.get_user_colors(user).items():
            user[key] = value

    titles = [
            ("Little Song Place", 2.0),
            ("Lumpy Space Princess", 0.2),
            ("Language Server Protocol", 0.1),
            ("Liskov Substitution Principle", 0.1),
    ]
    titles, weights = zip(*titles)
    title = random.choices(titles, weights)[0]

    page_songs = songs.get_latest(50)
    return render_template("index.html", users=all_users, songs=page_songs, page_title=title)

@app.get("/activity")
def activity():
    if not "userid" in session:
        return redirect("/login")

    # Get comment notifications
    notifications = db.query(
        """\
        select c.content, c.commentid, c.replytoid, cu.username as comment_username, rc.content as replyto_content, c.threadid, t.threadtype
        from notifications as n
        inner join comments as c on n.objectid == c.commentid
        inner join comment_threads as t on c.threadid = t.threadid
        left join comments as rc on c.replytoid == rc.commentid
        inner join users as cu on cu.userid == c.userid
        where (n.targetuserid = ?) and (n.objecttype = ?)
        order by c.created desc
        """,
        [session["userid"], comments.ObjectType.COMMENT])

    notifications = [dict(c) for c in notifications]
    for comment in notifications:
        threadtype = comment["threadtype"]
        if threadtype == comments.ThreadType.SONG:
            song = songs.by_threadid(comment["threadid"])
            comment["songid"] = song.songid
            comment["title"] = song.title
            comment["content_userid"] = song.userid
            comment["content_username"] = song.username
        elif threadtype == comments.ThreadType.PROFILE:
            profile = db.query("select * from users where threadid = ?", [comment["threadid"]], one=True)
            comment["content_userid"] = profile["userid"]
            comment["content_username"] = profile["username"]
        elif threadtype == comments.ThreadType.PLAYLIST:
            playlist = db.query(
                """\
                select * from playlists
                inner join users on playlists.userid == users.userid
                where playlists.threadid = ?
                """,
                [comment["threadid"]],
                one=True,
            )
            comment["playlistid"] = playlist["playlistid"]
            comment["name"] = playlist["name"]
            comment["content_userid"] = playlist["userid"]
            comment["content_username"] = playlist["username"]

    timestamp = datetime.now(timezone.utc).isoformat()
    db.query("update users set activitytime = ? where userid = ?", [timestamp, session["userid"]])
    db.commit()

    return render_template("activity.html", comments=notifications)

@app.get("/new-activity")
def new_activity():
    has_new_activity = False
    if "userid" in session:
        user_data = db.query("select activitytime from users where userid = ?", [session["userid"]], one=True)
        comment_data = db.query(
            """\
            select created from notifications
            where targetuserid = ?
            order by created desc
            limit 1""",
            [session["userid"]],
            one=True)

        if comment_data:
            comment_time = comment_data["created"]
            last_checked = user_data["activitytime"]

            if (last_checked is None) or (last_checked < comment_time):
                has_new_activity = True

    return {"new_activity": has_new_activity}

@app.get("/site-news")
def site_news():
    return render_template("news.html")

@app.post("/create-playlist")
def create_playlist():
    if not "userid" in session:
        return redirect("/login")

    name = request.form["name"]
    if not name or len(name) > 200:
        flash_and_log("Playlist must have a name", "error")
        return redirect(request.referrer)

    timestamp = datetime.now(timezone.utc).isoformat()

    private = request.form["type"] == "private"

    threadid = comments.create_thread(comments.ThreadType.PLAYLIST, session["userid"])

    db.query(
        "insert into playlists (created, updated, userid, name, private, threadid) values (?, ?, ?, ?, ?, ?)",
        args=[
            timestamp,
            timestamp,
            session["userid"],
            name,
            private,
            threadid
        ]
    )
    db.commit()
    flash_and_log(f"Created playlist {name}", "success")
    return redirect(request.referrer)

@app.get("/delete-playlist/<int:playlistid>")
def delete_playlist(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = db.query("select * from playlists where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Cannot delete other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    # Delete playlist
    db.query("delete from playlists where playlistid = ?", args=[playlistid])
    db.commit()

    flash_and_log(f"Deleted playlist {plist_data['name']}", "success")
    return redirect(f"/users/{session['username']}")

@app.post("/append-to-playlist")
def append_to_playlist():
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    try:
        playlistid = int(request.form["playlistid"])
    except ValueError:
        abort(400)

    plist_data = db.query("select * from playlists where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Cannot edit other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    songid = request.form["songid"]

    # Make sure song exists
    song_data = db.query("select * from songs where songid = ?", args=[songid], one=True)
    if not song_data:
        abort(404)

    # Set index to count of songs in list
    existing_songs = db.query("select * from playlist_songs where playlistid = ?", args=[playlistid])
    new_position = len(existing_songs)

    # Add to playlist
    db.query("insert into playlist_songs (playlistid, position, songid) values (?, ?, ?)", args=[playlistid, new_position, songid])

    # Update modification time
    timestamp = datetime.now(timezone.utc).isoformat()
    db.query("update playlists set updated = ? where playlistid = ?", args=[timestamp, playlistid])
    db.commit()

    flash_and_log(f"Added '{song_data['title']}' to {plist_data['name']}", "success")

    return {"status": "success", "messages": get_flashed_messages()}

@app.post("/edit-playlist/<int:playlistid>")
def edit_playlist_post(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = db.query("select * from playlists where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Cannot edit other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    # Make sure name is valid
    name = request.form["name"]
    if not name or len(name) > 200:
        flash_and_log("Playlist must have a name", "error")
        return redirect(request.referrer)

    # Make sure all songs are valid
    songids = []
    if request.form["songids"]:
        try:
            songids = [int(s) for s in request.form["songids"].split(",")]
        except ValueError:
            # Invalid songid(s)
            abort(400)

        for songid in songids:
            song_data = db.query("select * from songs where songid = ?", args=[songid])
            if not song_data:
                abort(400)

    # All songs valid - delete old songs
    db.query("delete from playlist_songs where playlistid = ?", args=[playlistid])

    # Re-add songs with new positions
    for position, songid in enumerate(songids):
        print(position, songid)
        db.query("insert into playlist_songs (playlistid, position, songid) values (?, ?, ?)", args=[playlistid, position, songid])

    # Update private, name
    private = int(request.form["type"] == "private")
    db.query("update playlists set private = ?, name = ? where playlistid = ?", [private, name, playlistid])

    db.commit()

    flash_and_log("Playlist updated", "success")
    return redirect(request.referrer)

@app.get("/playlists/<int:playlistid>")
def playlists(playlistid):

    # Make sure playlist exists
    plist_data = db.query("select * from playlists inner join users on playlists.userid = users.userid where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Protect private playlists
    if plist_data["private"]:
        if ("userid" not in session) or (session["userid"] != plist_data["userid"]):
            abort(404)  # Cannot view other user's private playlist - pretend it doesn't even exist

    # Get songs
    plist_songs = songs.get_for_playlist(playlistid)

    # Get comments
    plist_comments = comments.for_thread(plist_data["threadid"])

    # Show page
    return render_template(
            "playlist.html",
            name=plist_data["name"],
            playlistid=plist_data["playlistid"],
            private=plist_data["private"],
            userid=plist_data["userid"],
            username=plist_data["username"],
            threadid=plist_data["threadid"],
            **users.get_user_colors(plist_data),
            songs=plist_songs,
            comments=plist_comments)

def get_gif_data():
    gifs = []
    static_path = Path(__file__).parent / "static"
    for child in static_path.iterdir():
        if child.suffix == ".gif":
            with open(child, "rb") as gif:
                b64 = base64.b64encode(gif.read()).decode()
                gifs.append(f'<div class="img-data" id="{child.stem}" data-img-b64="{b64}"></div>')

    gifs = "\n".join(gifs)
    return gifs

def get_current_user_playlists():
    plist_data = []
    if "userid" in session:
        plist_data = db.query("select * from playlists where userid = ?", [session["userid"]])

    return plist_data

@app.context_processor
def inject_global_vars():
    return dict(
        gif_data=get_gif_data(),
        current_user_playlists=get_current_user_playlists(),
        **colors.DEFAULT_COLORS,
    )


################################################################################
# Generate Session Key
################################################################################

@app.cli.add_command
@click.command("gen-key")
def gen_key():
    """Generate a secret key for session cookie encryption"""
    import secrets
    print(secrets.token_hex())

