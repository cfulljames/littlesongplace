import base64
import enum
import json
import logging
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path, PosixPath
from typing import Optional

import bcrypt
import bleach
import click
from bleach.css_sanitizer import CSSSanitizer
from flask import Flask, render_template, request, redirect, g, session, abort, \
        send_from_directory, flash, get_flashed_messages
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

DB_VERSION = 4
DATA_DIR = Path(os.environ["DATA_DIR"]) if "DATA_DIR" in os.environ else Path(".")
SCRIPT_DIR = Path(__file__).parent

BGCOLOR = "#e8e6b5"
FGCOLOR = "#695c73"
ACCOLOR = "#9373a9"
DEFAULT_COLORS = dict(bgcolor=BGCOLOR, fgcolor=FGCOLOR, accolor=ACCOLOR)

################################################################################
# Logging
################################################################################

handler = RotatingFileHandler(DATA_DIR / "app.log", maxBytes=1_000_000, backupCount=10)
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

if "DATA_DIR" in os.environ:
    # Running on server behind proxy
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )
    app.logger.setLevel(logging.INFO)

@app.route("/")
def index():
    users = query_db("select * from users order by username asc")
    users = [dict(row) for row in users]
    for user in users:
        user["has_pfp"] = user_has_pfp(user["userid"])
        for key, value in get_user_colors(user).items():
            user[key] = value

    titles = [
            ("Little Song Place", 2.0),
            ("Lumpy Space Princess", 0.2),
            ("Language Server Protocol", 0.1),
            ("Liskov Substitution Principle", 0.1),
    ]
    titles, weights = zip(*titles)
    title = random.choices(titles, weights)[0]

    songs = Song.get_latest(50)
    return render_template("index.html", users=users, songs=songs, page_title=title)

@app.get("/signup")
def signup_get():
    return render_template("signup.html")

@app.post("/signup")
def signup_post():
    username = request.form["username"]
    password = request.form["password"]
    password_confirm = request.form["password_confirm"]

    error = False
    if not username.isidentifier():
        flash_and_log("Username cannot contain special characters", "error")
        error = True
    elif len(username) < 3:
        flash_and_log("Username must be at least 3 characters", "error")
        error = True
    elif len(username) > 30:
        flash_and_log("Username cannot be more than 30 characters", "error")
        error = True

    elif password != password_confirm:
        flash_and_log("Passwords do not match", "error")
        error = True
    elif len(password) < 8:
        flash_and_log("Password must be at least 8 characters", "error")
        error = True

    if query_db("select * from users where username = ?", [username], one=True):
        flash_and_log(f"Username '{username}' is already taken", "error")
        error = True

    if error:
        app.logger.info("Failed signup attempt")
        return redirect(request.referrer)

    password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    timestamp = datetime.now(timezone.utc).isoformat()
    query_db("insert into users (username, password, created) values (?, ?, ?)", [username, password, timestamp])
    get_db().commit()

    flash("User created.  Please sign in to continue.", "success")
    app.logger.info(f"Created user {username}")

    return redirect("/login")

@app.get("/login")
def login_get():
    return render_template("login.html")

@app.post("/login")
def login_post():
    username = request.form["username"]
    password = request.form["password"]

    user_data = query_db("select * from users where username = ?", [username], one=True)

    if user_data and bcrypt.checkpw(password.encode(), user_data["password"]):
        # Successful login
        session["username"] = username
        session["userid"] = user_data["userid"]
        session.permanent = True
        app.logger.info(f"{username} logged in")

        return redirect(f"/users/{username}")

    flash("Invalid username/password", "error")
    app.logger.info(f"Failed login for {username}")

    return render_template("login.html")


@app.get("/logout")
def logout():
    if "username" in session:
        session.pop("username")
    if "userid" in session:
        session.pop("userid")

    return redirect("/")

@app.get("/users/<profile_username>")
def users_profile(profile_username):

    # Look up user data for current profile
    profile_data = query_db("select * from users where username = ?", [profile_username], one=True)
    if profile_data is None:
        abort(404)
    profile_userid = profile_data["userid"]

    # Get playlists for current profile
    userid = session.get("userid", None)
    show_private = userid == profile_userid
    if show_private:
        plist_data = query_db("select * from playlists where userid = ? order by updated desc", [profile_userid])
    else:
        plist_data = query_db("select * from playlists where userid = ? and private = 0 order by updated desc", [profile_userid])

    # Get songs for current profile
    songs = Song.get_all_for_userid(profile_userid)

    # Sanitize bio
    profile_bio = ""
    if profile_data["bio"] is not None:
        profile_bio = sanitize_user_text(profile_data["bio"])

    return render_template(
            "profile.html",
            name=profile_username,
            userid=profile_userid,
            bio=profile_bio,
            **get_user_colors(profile_data),
            playlists=plist_data,
            songs=songs,
            user_has_pfp=user_has_pfp(profile_userid),
            is_profile_song_list=True)

@app.post("/edit-profile")
def edit_profile():
    if not "userid" in session:
        abort(401)

    query_db(
            "update users set bio = ?, bgcolor = ?, fgcolor = ?, accolor = ? where userid = ?",
            [request.form["bio"], request.form["bgcolor"], request.form["fgcolor"], request.form["accolor"], session["userid"]])
    get_db().commit()

    if request.files["pfp"]:
        pfp_path = get_user_images_path(session["userid"]) / "pfp.jpg"

        try:
            with Image.open(request.files["pfp"]) as im:
                # Drop alpha channel
                if im.mode in ("RGBA", "P"):
                    im = im.convert("RGB")

                target_size = 256  # Square (same width/height)
                # Resize
                if im.width >= im.height:
                    scale = 256 / im.height
                else:
                    scale = 256 / im.width

                im = im.resize((round(im.width*scale), round(im.height*scale)))

                # Crop to square
                center_h = im.width / 2
                center_v = im.height / 2
                left = center_h - (target_size // 2)
                right = center_h + (target_size // 2)
                top = center_v - (target_size // 2)
                bottom = center_v + (target_size // 2)
                im = im.crop((left, top, right, bottom))

                # Save to permanent location
                im.save(pfp_path)
        except UnidentifiedImageError:
            abort(400)  # Invalid image

    flash("Profile updated successfully")

    app.logger.info(f"{session['username']} updated bio")

    return redirect(f"/users/{session['username']}")

@app.get("/pfp/<int:userid>")
def pfp(userid):
    return send_from_directory(DATA_DIR / "images" / str(userid), "pfp.jpg")

@app.get("/edit-song")
def edit_song():
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    song = None

    colors = get_user_colors(session["userid"])

    if "songid" in request.args:
        try:
            songid = int(request.args["songid"])
        except ValueError:
            # Invalid song id - file not found
            app.logger.warning(f"Failed song edit - {session['username']} - invalid song ID {request.args['songid']}")
            abort(404)

        try:
            song = Song.by_id(songid)
            if not song.userid == session["userid"]:
                # Can't edit someone else's song - 401 unauthorized
                app.logger.warning(f"Failed song edit - {session['username']} - attempted update for unowned song")
                abort(401)
        except ValueError:
            # Song doesn't exist - 404 file not found
            app.logger.warning(f"Failed song edit - {session['username']} - song doesn't exist ({songid})")
            abort(404)

    return render_template("edit-song.html", song=song, **colors)

@app.post("/upload-song")
def upload_song():
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    userid = session["userid"]

    error = validate_song_form()

    if not error:
        if "songid" in request.args:
            error = update_song()
        else:
            error = create_song()

    if not error:
        username = session["username"]
        app.logger.info(f"{username} uploaded/modified a song")
        if "songid" in request.args:
            # After editing an existing song, go back to song page
            return redirect(f"/song/{userid}/{request.args['songid']}?action=view")
        else:
            # After creating a new song, go back to profile
            return redirect(f"/users/{username}")

    else:
        username = session["username"]
        app.logger.info(f"Failed song update - {username}")
        return redirect(request.referrer)

def validate_song_form():
    title = request.form["title"]
    description = request.form["description"]

    error = False

    # Check if title is valid
    if not title.isprintable():
        flash_and_log(f"'{title}' is not a valid song title", "error")
        error = True
    elif len(title) > 80:
        flash_and_log(f"Title cannot be more than 80 characters", "error")
        error = True

    # Check if description is valid
    if len(description) > 10_000:
        flash_and_log(f"Description cannot be more than 10k characters", "error")
        error = True

    # Check if tags are valid
    tags = request.form["tags"]
    tags = [t.strip() for t in tags.split(",")]
    for tag in tags:
        if not tag.isprintable() or len(tag) > 30:
            flash_and_log(f"'{tag}' is not a valid tag name", "error")
            error = True

    # Check if collaborators are valid
    collaborators = request.form["collabs"]
    collaborators = [c.strip() for c in collaborators.split(",")]
    for collab in collaborators:
        if not collab.isprintable() or len(collab) > 31:  # 30ch username + @
            flash_and_log(f"'{collab}' is not a valid collaborator name", "error")
            error = True

    return error

def get_user_songs_path(userid):
    userpath = DATA_DIR / "songs" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def get_user_images_path(userid):
    userpath = DATA_DIR / "images" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def update_song():
    songid = request.args["songid"]
    try:
        int(songid)
    except ValueError:
        abort(400)

    file = request.files["song-file"] if "song-file" in request.files else None
    yt_url = request.form["song-url"] if "song-url" in request.form else None
    title = request.form["title"]
    description = request.form["description"]
    tags = [t.strip() for t in request.form["tags"].split(",") if t]
    collaborators = [c.strip() for c in request.form["collabs"].split(",") if c]

    # Make sure song exists and the logged-in user owns it
    song_data = query_db("select * from songs where songid = ?", [songid], one=True)
    if song_data is None:
        abort(400)
    elif session["userid"] != song_data["userid"]:
        abort(401)

    error = False
    if file or yt_url:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            passed = convert_song(tmp_file, file, yt_url)

            if passed:
                # Move file to permanent location
                filepath = get_user_songs_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")
                shutil.move(tmp_file.name, filepath)
            else:
                error = True

    if not error:
        # Update songs table
        query_db(
                "update songs set title = ?, description = ? where songid = ?",
                [title, description, songid])

        # Update song_tags table
        query_db("delete from song_tags where songid = ?", [songid])
        for tag in tags:
            query_db("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

        # Update song_collaborators table
        query_db("delete from song_collaborators where songid = ?", [songid])
        for collab in collaborators:
            query_db("insert into song_collaborators (name, songid) values (?, ?)", [collab, songid])

        get_db().commit()
        flash_and_log(f"Successfully updated '{title}'", "success")

    return error

def create_song():
    file = request.files["song-file"] if "song-file" in request.files else None
    yt_url = request.form["song-url"] if "song-url" in request.form else None
    title = request.form["title"]
    description = request.form["description"]
    tags = [t.strip() for t in request.form["tags"].split(",") if t]
    collaborators = [c.strip() for c in request.form["collabs"].split(",") if c]

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        passed = convert_song(tmp_file, file, yt_url)

        if not passed:
            return True
        else:
            # Create song
            timestamp = datetime.now(timezone.utc).isoformat()
            song_data = query_db(
                    "insert into songs (userid, title, description, created) values (?, ?, ?, ?) returning (songid)",
                    [session["userid"], title, description, timestamp], one=True)
            songid = song_data["songid"]
            filepath = get_user_songs_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")

            # Move file to permanent location
            shutil.move(tmp_file.name, filepath)

            # Assign tags
            for tag in tags:
                query_db("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

            # Assign collaborators
            for collab in collaborators:
                query_db("insert into song_collaborators (songid, name) values (?, ?)", [songid, collab])

            get_db().commit()

            flash_and_log(f"Successfully uploaded '{title}'", "success")
            return False

def convert_song(tmp_file, request_file, yt_url):
    if request_file:
        # Get uploaded file
        request_file.save(tmp_file)
        tmp_file.close()
    else:
        # Import from YouTube
        tmp_file.close()
        os.unlink(tmp_file.name)  # Delete file so yt-dlp doesn't complain
        try:
            yt_import(tmp_file, yt_url)
        except DownloadError:
            flash_and_log(f"Failed to import from YouTube URL: {yt_url}")
            return False

    result = subprocess.run(["mpck", tmp_file.name], stdout=subprocess.PIPE)
    res_stdout = result.stdout.decode()
    app.logger.info(f"mpck result: \n {res_stdout}")
    lines = res_stdout.split("\n")
    lines = [l.strip().lower() for l in lines]
    if any(l.startswith("result") and l.endswith("ok") for l in lines):
        # Uploaded valid mp3 file
        return True

    # Not a valid mp3, try to convert with ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as out_file:
        out_file.close()
        os.remove(out_file.name)
        result = subprocess.run(["ffmpeg", "-i", tmp_file.name, out_file.name], stdout=subprocess.PIPE)
        if result.returncode == 0:
            # Successfully converted file, overwrite original file
            os.replace(out_file.name, tmp_file.name)
            return True

        if os.path.exists(out_file.name):
            os.remove(out_file.name)

    flash_and_log("Invalid audio file", "error")
    return False

def yt_import(tmp_file, yt_url):
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': tmp_file.name,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([yt_url])

@app.get("/delete-song/<int:songid>")
def delete_song(songid):

    song_data = query_db("select * from songs where songid = ?", [songid], one=True)

    if not song_data:
        app.logger.warning(f"Failed song delete - {session['username']} - song doesn't exist")
        abort(404)  # Song doesn't exist

    # Users can only delete their own songs
    if song_data["userid"] != session["userid"]:
        app.logger.warning(f"Failed song delete - {session['username']} - user doesn't own song")
        abort(401)

    # Delete tags, collaborators
    query_db("delete from song_tags where songid = ?", [songid])
    query_db("delete from song_collaborators where songid = ?", [songid])

    # Delete song database entry
    query_db("delete from songs where songid = ?", [songid])
    get_db().commit()

    # Delete song file from disk
    songpath = DATA_DIR / "songs" / str(session["userid"]) / (str(songid) + ".mp3")
    if songpath.exists():
        os.remove(songpath)

    app.logger.info(f"{session['username']} deleted song: {song_data['title']}")
    flash_and_log(f"Deleted '{song_data['title']}'", "success")

    return redirect(f"/users/{session['username']}")

@app.get("/song/<int:userid>/<int:songid>")
def song(userid, songid):
    if request.args.get("action", None) == "view":
        try:
            song = Song.by_id(songid)
            if song.userid != userid:
                abort(404)

            return render_template(
                    "song.html",
                    songs=[song],
                    song=song,
                    **get_user_colors(userid))
        except ValueError:
            abort(404)
    else:
        return send_from_directory(DATA_DIR / "songs" / str(userid), str(songid) + ".mp3")

@app.get("/songs")
def songs():
    tag = request.args.get("tag", None)
    user = request.args.get("user", None)

    colors = DEFAULT_COLORS
    if user:
        colors = get_user_colors(user)

    if tag and user:
        songs = Song.get_all_for_username_and_tag(user, tag)
    elif tag:
        songs = Song.get_all_for_tag(tag)
    elif user:
        songs = Song.get_all_for_username(user)
    else:
        songs = Song.get_random(50)

    return render_template("songs-by-tag.html", user=user, tag=tag, songs=songs, **colors)

@app.route("/comment", methods=["GET", "POST"])
def comment():
    if not "userid" in session:
        return redirect("/login")

    if not "songid" in request.args:
        abort(400) # Must have songid

    try:
        # TODO: Handle other comment types
        song = Song.by_id(request.args["songid"])
    except ValueError:
        abort(404) # Invald songid

    # Check for comment being replied to
    replyto = None
    if "replytoid" in request.args:
        replytoid = request.args["replytoid"]
        replyto = query_db("select * from comments inner join users on comments.userid == users.userid where commentid = ?", [replytoid], one=True)
        if not replyto:
            abort(404) # Invalid comment

    # Check for comment being edited
    comment = None
    if "commentid" in request.args:
        commentid = request.args["commentid"]
        comment = query_db("select * from comments inner join users on comments.userid == users.userid where commentid = ?", [commentid], one=True)
        if not comment:
            abort(404) # Invalid comment
        if comment["userid"] != session["userid"]:
            abort(403) # User doesn't own this comment

    if request.method == "GET":
        # Show the comment editor
        session["previous_page"] = request.referrer
        # TODO: update page to handle other comment types
        return render_template("comment.html", song=song, replyto=replyto, comment=comment)

    elif request.method == "POST":
        # Add/update comment (user clicked the Post Comment button)
        content = request.form["content"]
        if comment:
            # Update existing comment
            query_db("update comments set content = ? where commentid = ?", args=[content, comment["commentid"]])
        else:
            # Add new comment
            timestamp = datetime.now(timezone.utc).isoformat()
            userid = session["userid"]
            songid = request.args["songid"]
            replytoid = request.args.get("replytoid", None)

            comment = query_db(
                    "insert into comments (threadid, userid, replytoid, created, content) values (?, ?, ?, ?, ?) returning (commentid)",
                    args=[threadid, userid, replytoid, timestamp, content], one=True)
            commentid = comment["commentid"]

            # TODO: Notify content owner
            # Notify song owner
            notification_targets = {song.userid}
            if replyto:
                # Notify parent commenter
                notification_targets.add(replyto["userid"])

                # Notify previous repliers in thread
                previous_replies = query_db("select * from comments where replytoid = ?", [replytoid])
                for reply in previous_replies:
                    notification_targets.add(reply["userid"])

            # Don't notify the person who wrote the comment
            if userid in notification_targets:
                notification_targets.remove(userid)

            # Create notifications
            for target in notification_targets:
                query_db("insert into comment_notifications (commentid, targetuserid) values (?, ?)", [commentid, target])

        get_db().commit()

        return redirect_to_previous_page()

def redirect_to_previous_page():
    previous_page = "/"
    if "previous_page" in session:
        previous_page = session["previous_page"]
        session.pop("previous_page")
    return redirect(previous_page)

@app.get("/delete-comment/<int:commentid>")
def comment_delete(commentid):
    if "userid" not in session:
        return redirect("/login")

    # TODO: Handle non-song comments
    comment = query_db("select c.userid as comment_user, s.userid as song_user from comments as c inner join songs as s on c.songid == s.songid where commentid = ?", [commentid], one=True)
    if not comment:
        abort(404) # Invalid comment

    # Only commenter and song owner can delete comments
    if not ((comment["comment_user"] == session["userid"])
            or (comment["song_user"] == session["userid"])):
        abort(403)

    query_db("delete from comments where (commentid = ?) or (replytoid = ?)", [commentid, commentid])
    get_db().commit()

    return redirect(request.referrer)

@app.get("/activity")
def activity():
    if not "userid" in session:
        return redirect("/login")

    # TODO: Handle other comment types
    # Get comment notifications
    comments = query_db(
        """\
        select c.content, c.commentid, c.replytoid, cu.username as comment_username, s.songid, s.title, s.userid as song_userid, su.username as song_username, rc.content as replyto_content
        from comment_notifications as cn
        inner join comments as c on cn.commentid == c.commentid
        left join comments as rc on c.replytoid == rc.commentid
        inner join songs as s on c.songid == s.songid
        inner join users as su on su.userid == s.userid
        inner join users as cu on cu.userid == c.userid
        where cn.targetuserid = ?
        order by c.created desc
        """,
        [session["userid"]])

    timestamp = datetime.now(timezone.utc).isoformat()
    query_db("update users set activitytime = ? where userid = ?", [timestamp, session["userid"]])
    get_db().commit()

    return render_template("activity.html", comments=comments)

@app.get("/new-activity")
def new_activity():
    has_new_activity = False
    if "userid" in session:
        user_data = query_db("select activitytime from users where userid = ?", [session["userid"]], one=True)
        comment_data = query_db(
            """\
            select sc.created from comment_notifications as cn
            inner join comments as c on cn.commentid = c.commentid
            where cn.targetuserid = ?
            order by c.created desc
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

    query_db(
        "insert into playlists (created, updated, userid, name, private) values (?, ?, ?, ?, ?)",
        args=[
            timestamp,
            timestamp,
            session["userid"],
            name,
            private,
        ]
    )
    get_db().commit()
    flash_and_log(f"Created playlist {name}", "success")
    return redirect(request.referrer)

@app.get("/delete-playlist/<int:playlistid>")
def delete_playlist(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = query_db("select * from playlists where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Cannot delete other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    # Delete playlist
    query_db("delete from playlists where playlistid = ?", args=[playlistid])
    get_db().commit()

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

    plist_data = query_db("select * from playlists where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Cannot edit other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    songid = request.form["songid"]

    # Make sure song exists
    song_data = query_db("select * from songs where songid = ?", args=[songid], one=True)
    if not song_data:
        abort(404)

    # Set index to count of songs in list
    existing_songs = query_db("select * from playlist_songs where playlistid = ?", args=[playlistid])
    new_position = len(existing_songs)

    # Add to playlist
    query_db("insert into playlist_songs (playlistid, position, songid) values (?, ?, ?)", args=[playlistid, new_position, songid])

    # Update modification time
    timestamp = datetime.now(timezone.utc).isoformat()
    query_db("update playlists set updated = ? where playlistid = ?", args=[timestamp, playlistid])
    get_db().commit()

    flash_and_log(f"Added '{song_data['title']}' to {plist_data['name']}", "success")

    return {"status": "success", "messages": get_flashed_messages()}

@app.post("/edit-playlist/<int:playlistid>")
def edit_playlist_post(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = query_db("select * from playlists where playlistid = ?", args=[playlistid], one=True)
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
            song_data = query_db("select * from songs where songid = ?", args=[songid])
            if not song_data:
                abort(400)

    # All songs valid - delete old songs
    query_db("delete from playlist_songs where playlistid = ?", args=[playlistid])

    # Re-add songs with new positions
    for position, songid in enumerate(songids):
        print(position, songid)
        query_db("insert into playlist_songs (playlistid, position, songid) values (?, ?, ?)", args=[playlistid, position, songid])

    # Update private, name
    private = int(request.form["type"] == "private")
    query_db("update playlists set private = ?, name = ? where playlistid = ?", [private, name, playlistid])

    get_db().commit()

    flash_and_log("Playlist updated", "success")
    return redirect(request.referrer)

@app.get("/playlists/<int:playlistid>")
def playlists(playlistid):

    # Make sure playlist exists
    plist_data = query_db("select * from playlists inner join users on playlists.userid = users.userid where playlistid = ?", args=[playlistid], one=True)
    if not plist_data:
        abort(404)

    # Protect private playlists
    if plist_data["private"]:
        if ("userid" not in session) or (session["userid"] != plist_data["userid"]):
            abort(404)  # Cannot view other user's private playlist - pretend it doesn't even exist

    # Get songs
    songs = Song.get_for_playlist(playlistid)

    # Show page
    return render_template(
            "playlist.html",
            name=plist_data["name"],
            playlistid=plist_data["playlistid"],
            private=plist_data["private"],
            userid=plist_data["userid"],
            username=plist_data["username"],
            **get_user_colors(plist_data),
            songs=songs)

def flash_and_log(msg, category=None):
    flash(msg, category)
    username = session["username"] if "username" in session else "N/A"
    url = request.referrer
    logmsg = f"[{category}] User: {username}, URL: {url} - {msg}"
    if category == "error":
        app.logger.warning(logmsg)
    else:
        app.logger.info(logmsg)

def sanitize_user_text(text):
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS.union({
            'area', 'br', 'div', 'img', 'map', 'hr', 'header', 'hgroup', 'table', 'tr', 'td',
            'th', 'thead', 'tbody', 'span', 'small', 'p', 'q', 'u', 'pre',
        })
        allowed_attributes = {
            "*": ["style"], "a": ["href", "title"], "abbr": ["title"], "acronym": ["title"],
            "img": ["src", "alt", "usemap", "width", "height"], "map": ["name"],
            "area": ["shape", "coords", "alt", "href"]
        }
        allowed_css_properties = {
            "font-size", "font-style", "font-variant", "font-family", "font-weight", "color",
            "background-color", "background-image", "border", "border-color",
            "border-image", "width", "height"
        }
        css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_css_properties)
        return bleach.clean(
                text,
                tags=allowed_tags,
                attributes=allowed_attributes,
                css_sanitizer=css_sanitizer)

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
        plist_data = query_db("select * from playlists where userid = ?", [session["userid"]])

    return plist_data

def get_user_colors(user_data):
    if isinstance(user_data, int):
        # Get colors for userid
        user_data = query_db("select * from users where userid = ?", [user_data], one=True)
    elif isinstance(user_data, str):
        # Get colors for username
        user_data = query_db("select * from users where username = ?", [user_data], one=True)

    colors = dict(bgcolor=BGCOLOR, fgcolor=FGCOLOR, accolor=ACCOLOR)
    for key in colors:
        if user_data[key]:
            colors[key] = user_data[key]

    return colors

def user_has_pfp(userid):
    return (get_user_images_path(userid)/"pfp.jpg").exists()

@app.context_processor
def inject_global_vars():
    return dict(
        gif_data=get_gif_data(),
        current_user_playlists=get_current_user_playlists(),
        **DEFAULT_COLORS,
    )


################################################################################
# Database
################################################################################

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATA_DIR / "database.db")
        db.cursor().execute("PRAGMA foreign_keys = ON")
        db.row_factory = sqlite3.Row

        # Get current version
        user_version = query_db("pragma user_version", one=True)[0]

        # Run update script if DB is out of date
        schema_update_script = SCRIPT_DIR / 'schema_update.sql'
        if user_version < DB_VERSION and schema_update_script.exists():
            with app.open_resource(schema_update_script, mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()

            if DB_VERSION == 4:
                # TODO: Remove after deploying
                assign_thread_ids(db, "songs", "songid", threadtype=ThreadType.SONG)
                assign_thread_ids(db, "users", "userid", threadtype=ThreadType.PROFILE)
                assign_thread_ids(db, "playlists", "playlistid", threadtype=ThreadType.PLAYLIST)

                # Copy song comments to new comments table
                cur = db.execute(
                    """\
                    select commentid, threadid, sc.userid, replytoid, sc.created, content
                    from song_comments as sc
                    inner join songs on sc.songid = songs.songid
                    """)
                for row in cur:
                    comment_cur = db.execute(
                        """\
                        insert into comments (commentid, threadid, userid, replytoid, created, content)
                        values (?, ?, ?, ?, ?, ?)
                        """,
                        [row["commentid"], row["threadid"], row["userid"], row["replytoid"], row["created"], row["content"]])
                    comment_cur.close()
                cur.close()

                # Copy song comment notifications to new comment notifications table
                cur = db.execute(
                    """\
                    insert into comment_notifications
                    select * from song_comment_notifications
                    """)

                db.execute("PRAGMA user_version = 4").close()

                db.commit()

    return db

# TODO: Remove after deploying
def assign_thread_ids(db, table, id_col, threadtype):
    cur = db.execute(f"select * from {table}")
    for row in cur:
        thread_cur = db.execute("insert into comment_threads (threadtype) values (?) returning threadid", [threadtype])
        threadid = thread_cur.fetchone()[0]
        thread_cur.close()

        song_cur = db.execute(f"update {table} set threadid = ? where {id_col} = ?", [threadid, row[id_col]])
        song_cur.close()
    cur.close()

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.cli.add_command
@click.command("init-db")
def init_db():
    """Clear the existing data and create new tables"""
    with app.app_context():
        db = sqlite3.connect(DATA_DIR / "database.db")
        with app.open_resource(SCRIPT_DIR / 'schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

################################################################################
# Generate Session Key
################################################################################

@app.cli.add_command
@click.command("gen-key")
def gen_key():
    """Generate a secret key for session cookie encryption"""
    import secrets
    print(secrets.token_hex())

class ThreadType(enum.IntEnum):
    SONG = 0
    PROFILE = 1
    PLAYLIST = 2

@dataclass
class Song:
    songid: int
    userid: int
    threadid: int
    username: str
    title: str
    description: str
    created: str
    tags: list[str]
    collaborators: list[str]
    user_has_pfp: bool

    def json(self):
        return json.dumps(vars(self))

    def get_comments(self):
        comments = query_db("select * from comments inner join users on comments.userid == users.userid where threadid = ?", [self.threadid])
        comments = [dict(c) for c in comments]
        for c in comments:
            c["content"] = sanitize_user_text(c["content"])

        # Top-level comments
        song_comments = sorted([dict(c) for c in comments if c["replytoid"] is None], key=lambda c: c["created"])
        song_comments = list(reversed(song_comments))
        # Replies (can only reply to top-level)
        for comment in song_comments:
            comment["replies"] = sorted([c for c in comments if c["replytoid"] == comment["commentid"]], key=lambda c: c["created"])

        return song_comments

    @classmethod
    def by_id(cls, songid):
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songid = ?", [songid])
        if not songs:
            raise ValueError(f"No song for ID {songid:d}")

        return songs[0]

    @classmethod
    def get_all_for_userid(cls, userid):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid where songs.userid = ? order by songs.created desc", [userid])

    @classmethod
    def get_all_for_username(cls, username):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid where users.username = ? order by songs.created desc", [username])

    @classmethod
    def get_all_for_username_and_tag(cls, username, tag):
        return cls._from_db(f"select * from song_tags inner join songs on song_tags.songid = songs.songid inner join users on songs.userid = users.userid where (username = ? and tag = ?) order by songs.created desc", [username, tag])

    @classmethod
    def get_all_for_tag(cls, tag):
        return cls._from_db(f"select * from song_tags inner join songs on song_tags.songid = songs.songid inner join users on songs.userid = users.userid where (tag = ?) order by songs.created desc", [tag])

    @classmethod
    def get_latest(cls, count):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid order by songs.created desc limit ?", [count])

    @classmethod
    def get_random(cls, count):
        # Get random songs + 10 extras so I can filter out my own (I uploaded too many :/)
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songid in (select songid from songs order by random() limit ?)", [count + 10])
        random.shuffle(songs)

        # Prevent my songs from showing up in the first 10 results
        for i in reversed(range(min(10, len(songs)))):
            if songs[i].username == "cfulljames":
                del songs[i]

        # Drop any extra songs (since we asked for 10 extras)
        songs = songs[:count]

        return songs

    @classmethod
    def get_for_playlist(cls, playlistid):
        return cls._from_db("""\
            select * from playlist_songs
            inner join songs on playlist_songs.songid = songs.songid
            inner join users on songs.userid = users.userid
            where playlistid = ?
            order by playlist_songs.position asc
            """, [playlistid])

    @classmethod
    def _from_db(cls, query, args=()):
        songs_data = query_db(query, args)
        tags, collabs = cls._get_info_for_songs(songs_data)
        songs = []
        for sd in songs_data:
            song_tags = [t["tag"] for t in tags[sd["songid"]] if t["tag"]]
            song_collabs = [c["name"] for c in collabs[sd["songid"]] if c["name"]]
            created = datetime.fromisoformat(sd["created"]).astimezone().strftime("%Y-%m-%d")
            has_pfp = user_has_pfp(sd["userid"])
            songs.append(cls(sd["songid"], sd["userid"], sd["username"], sd["title"], sanitize_user_text(sd["description"]), created, song_tags, song_collabs, has_pfp))
        return songs

    @classmethod
    def _get_info_for_songs(cls, songs):
        tags = {}
        collabs = {}
        for song in songs:
            songid = song["songid"]
            tags[songid] = query_db("select (tag) from song_tags where songid = ?", [songid])
            collabs[songid] = query_db("select (name) from song_collaborators where songid = ?", [songid])
        return tags, collabs


