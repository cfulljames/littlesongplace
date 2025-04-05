import base64
import enum
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path, PosixPath
from typing import Optional

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

from . import auth, comments, datadir, db
from .logutils import flash_and_log

BGCOLOR = "#e8e6b5"
FGCOLOR = "#695c73"
ACCOLOR = "#9373a9"
DEFAULT_COLORS = dict(bgcolor=BGCOLOR, fgcolor=FGCOLOR, accolor=ACCOLOR)

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
db.init_app(app)

if "DATA_DIR" in os.environ:
    # Running on server behind proxy
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )
    app.logger.setLevel(logging.INFO)

@app.route("/")
def index():
    users = db.query("select * from users order by username asc")
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

@app.get("/users/<profile_username>")
def users_profile(profile_username):

    # Look up user data for current profile
    profile_data = db.query("select * from users where username = ?", [profile_username], one=True)
    if profile_data is None:
        abort(404)
    profile_userid = profile_data["userid"]

    # Get playlists for current profile
    userid = session.get("userid", None)
    show_private = userid == profile_userid
    if show_private:
        plist_data = db.query("select * from playlists where userid = ? order by updated desc", [profile_userid])
    else:
        plist_data = db.query("select * from playlists where userid = ? and private = 0 order by updated desc", [profile_userid])

    # Get songs for current profile
    songs = Song.get_all_for_userid(profile_userid)

    # Get comments for current profile
    profile_comments = get_comments(profile_data["threadid"])

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
            comments=profile_comments,
            threadid=profile_data["threadid"],
            user_has_pfp=user_has_pfp(profile_userid))

@app.post("/edit-profile")
def edit_profile():
    if not "userid" in session:
        abort(401)

    db.query(
            "update users set bio = ?, bgcolor = ?, fgcolor = ?, accolor = ? where userid = ?",
            [request.form["bio"], request.form["bgcolor"], request.form["fgcolor"], request.form["accolor"], session["userid"]])
    db.commit()

    if request.files["pfp"]:
        pfp_path = datadir.get_user_images_path(session["userid"]) / "pfp.jpg"

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
    return send_from_directory(datadir.get_user_images_path(userid), "pfp.jpg")

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
    song_data = db.query("select * from songs where songid = ?", [songid], one=True)
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
                filepath = datadir.get_user_songs_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")
                shutil.move(tmp_file.name, filepath)
            else:
                error = True

    if not error:
        # Update songs table
        db.query(
                "update songs set title = ?, description = ? where songid = ?",
                [title, description, songid])

        # Update song_tags table
        db.query("delete from song_tags where songid = ?", [songid])
        for tag in tags:
            db.query("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

        # Update song_collaborators table
        db.query("delete from song_collaborators where songid = ?", [songid])
        for collab in collaborators:
            db.query("insert into song_collaborators (name, songid) values (?, ?)", [collab, songid])

        db.commit()
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
            # Create comment thread
            threadid = comments.create_thread(comments.ThreadType.SONG, session["userid"])
            # Create song
            timestamp = datetime.now(timezone.utc).isoformat()
            song_data = db.query(
                    "insert into songs (userid, title, description, created, threadid) values (?, ?, ?, ?, ?) returning (songid)",
                    [session["userid"], title, description, timestamp, threadid], one=True)
            songid = song_data["songid"]
            filepath = datadir.get_user_songs_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")

            # Move file to permanent location
            shutil.move(tmp_file.name, filepath)

            # Assign tags
            for tag in tags:
                db.query("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

            # Assign collaborators
            for collab in collaborators:
                db.query("insert into song_collaborators (songid, name) values (?, ?)", [songid, collab])

            db.commit()

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
        except DownloadError as ex:
            app.logger.warning(str(ex))
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
        print(result)
        if result.returncode == 0:
            print('okie')
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
        'logger': app.logger,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([yt_url])

@app.get("/delete-song/<int:songid>")
def delete_song(songid):

    song_data = db.query("select * from songs where songid = ?", [songid], one=True)

    if not song_data:
        app.logger.warning(f"Failed song delete - {session['username']} - song doesn't exist")
        abort(404)  # Song doesn't exist

    # Users can only delete their own songs
    if song_data["userid"] != session["userid"]:
        app.logger.warning(f"Failed song delete - {session['username']} - user doesn't own song")
        abort(401)

    # Delete tags, collaborators
    db.query("delete from song_tags where songid = ?", [songid])
    db.query("delete from song_collaborators where songid = ?", [songid])

    # Delete song database entry
    db.query("delete from songs where songid = ?", [songid])
    db.commit()

    # Delete song file from disk
    songpath = datadir.get_user_songs_path(session["userid"]) / (str(songid) + ".mp3")
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
        return send_from_directory(datadir.get_user_songs_path(userid), str(songid) + ".mp3")

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

    if not "threadid" in request.args:
        abort(400) # Must have threadid

    thread = db.query("select * from comment_threads where threadid = ?", [request.args["threadid"]], one=True)
    if not thread:
        abort(404) # Invalid threadid

    # Check for comment being replied to
    replyto = None
    if "replytoid" in request.args:
        replytoid = request.args["replytoid"]
        replyto = db.query("select * from comments inner join users on comments.userid == users.userid where commentid = ?", [replytoid], one=True)
        if not replyto:
            abort(404) # Invalid comment

    # Check for comment being edited
    comment = None
    if "commentid" in request.args:
        commentid = request.args["commentid"]
        comment = db.query("select * from comments inner join users on comments.userid == users.userid where commentid = ?", [commentid], one=True)
        if not comment:
            abort(404) # Invalid comment
        if comment["userid"] != session["userid"]:
            abort(403) # User doesn't own this comment

    if request.method == "GET":
        # Show the comment editor
        session["previous_page"] = request.referrer
        threadtype = thread["threadtype"]
        song = None
        profile = None
        playlist = None
        if threadtype == comments.ThreadType.SONG:
            song = Song.by_threadid(request.args["threadid"])
        elif threadtype == comments.ThreadType.PROFILE:
            profile = db.query("select * from users where threadid = ?", [request.args["threadid"]], one=True)
        elif threadtype == comments.ThreadType.PLAYLIST:
            profile = db.query("select * from playlists inner join users on playlists.userid = users.userid where playlists.threadid = ?", [request.args["threadid"]], one=True)
        return render_template(
            "comment.html",
            song=song,
            profile=profile,
            playlist=playlist,
            replyto=replyto,
            comment=comment,
        )

    elif request.method == "POST":
        # Add/update comment (user clicked the Post Comment button)
        content = request.form["content"]
        if comment:
            # Update existing comment
            db.query("update comments set content = ? where commentid = ?", args=[content, comment["commentid"]])
        else:
            # Add new comment
            timestamp = datetime.now(timezone.utc).isoformat()
            userid = session["userid"]
            replytoid = request.args.get("replytoid", None)

            threadid = request.args["threadid"]
            comment = db.query(
                    "insert into comments (threadid, userid, replytoid, created, content) values (?, ?, ?, ?, ?) returning (commentid)",
                    args=[threadid, userid, replytoid, timestamp, content], one=True)
            commentid = comment["commentid"]

            # Notify content owner
            notification_targets = {thread["userid"]}
            if replyto:
                # Notify parent commenter
                notification_targets.add(replyto["userid"])

                # Notify previous repliers in thread
                previous_replies = db.query("select * from comments where replytoid = ?", [replytoid])
                for reply in previous_replies:
                    notification_targets.add(reply["userid"])

            # Don't notify the person who wrote the comment
            if userid in notification_targets:
                notification_targets.remove(userid)

            # Create notifications
            for target in notification_targets:
                db.query("insert into notifications (objectid, objecttype, targetuserid, created) values (?, ?, ?, ?)", [commentid, ObjectType.COMMENT, target, timestamp])

        db.commit()

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

    comment = db.query("select c.userid as comment_user, t.userid as thread_user from comments as c inner join comment_threads as t on c.threadid == t.threadid where commentid = ?", [commentid], one=True)
    if not comment:
        abort(404) # Invalid comment

    # Only commenter and song owner can delete comments
    if not ((comment["comment_user"] == session["userid"])
            or (comment["thread_user"] == session["userid"])):
        abort(403)

    db.query("delete from comments where (commentid = ?) or (replytoid = ?)", [commentid, commentid])
    db.commit()

    return redirect(request.referrer)

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
        [session["userid"], ObjectType.COMMENT])

    notifications = [dict(c) for c in notifications]
    for comment in notifications:
        threadtype = comment["threadtype"]
        if threadtype == comments.ThreadType.SONG:
            song = Song.by_threadid(comment["threadid"])
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
    songs = Song.get_for_playlist(playlistid)

    # Get comments
    plist_comments = get_comments(plist_data["threadid"])

    # Show page
    return render_template(
            "playlist.html",
            name=plist_data["name"],
            playlistid=plist_data["playlistid"],
            private=plist_data["private"],
            userid=plist_data["userid"],
            username=plist_data["username"],
            threadid=plist_data["threadid"],
            **get_user_colors(plist_data),
            songs=songs,
            comments=plist_comments)

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

def get_comments(threadid):
    thread_comments = db.query("select * from comments inner join users on comments.userid == users.userid where comments.threadid = ?", [threadid])
    thread_comments = [dict(c) for c in thread_comments]
    for c in thread_comments:
        c["content"] = sanitize_user_text(c["content"])

    # Top-level comments
    song_comments = sorted([dict(c) for c in thread_comments if c["replytoid"] is None], key=lambda c: c["created"])
    song_comments = list(reversed(song_comments))
    # Replies (can only reply to top-level)
    for comment in song_comments:
        comment["replies"] = sorted([c for c in thread_comments if c["replytoid"] == comment["commentid"]], key=lambda c: c["created"])

    return song_comments

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

def get_user_colors(user_data):
    if isinstance(user_data, int):
        # Get colors for userid
        user_data = db.query("select * from users where userid = ?", [user_data], one=True)
    elif isinstance(user_data, str):
        # Get colors for username
        user_data = db.query("select * from users where username = ?", [user_data], one=True)

    colors = dict(bgcolor=BGCOLOR, fgcolor=FGCOLOR, accolor=ACCOLOR)
    for key in colors:
        if user_data and user_data[key]:
            colors[key] = user_data[key]

    return colors

def user_has_pfp(userid):
    return (datadir.get_user_images_path(userid)/"pfp.jpg").exists()

@app.context_processor
def inject_global_vars():
    return dict(
        gif_data=get_gif_data(),
        current_user_playlists=get_current_user_playlists(),
        **DEFAULT_COLORS,
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

class ObjectType(enum.IntEnum):
    COMMENT = 0

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
        return get_comments(self.threadid)

    @classmethod
    def by_id(cls, songid):
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songid = ?", [songid])
        if not songs:
            raise ValueError(f"No song for ID {songid:d}")

        return songs[0]

    @classmethod
    def by_threadid(cls, threadid):
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songs.threadid = ?", [threadid])
        if not songs:
            raise ValueError(f"No song for Thread ID {songid:d}")

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
        songs_data = db.query(query, args)
        tags, collabs = cls._get_info_for_songs(songs_data)
        songs = []
        for sd in songs_data:
            song_tags = [t["tag"] for t in tags[sd["songid"]] if t["tag"]]
            song_collabs = [c["name"] for c in collabs[sd["songid"]] if c["name"]]
            created = datetime.fromisoformat(sd["created"]).astimezone().strftime("%Y-%m-%d")
            has_pfp = user_has_pfp(sd["userid"])
            songs.append(cls(sd["songid"], sd["userid"], sd["threadid"], sd["username"], sd["title"], sanitize_user_text(sd["description"]), created, song_tags, song_collabs, has_pfp))
        return songs

    @classmethod
    def _get_info_for_songs(cls, songs):
        tags = {}
        collabs = {}
        for song in songs:
            songid = song["songid"]
            tags[songid] = db.query("select (tag) from song_tags where songid = ?", [songid])
            collabs[songid] = db.query("select (name) from song_collaborators where songid = ?", [songid])
        return tags, collabs


