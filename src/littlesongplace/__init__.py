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
app.register_blueprint(profiles.bp)
app.register_blueprint(comments.bp)
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

    page_songs = songs.Song.get_latest(50)
    return render_template("index.html", users=all_users, songs=page_songs, page_title=title)

@app.get("/edit-song")
def edit_song():
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    song = None

    colors = users.get_user_colors(session["userid"])

    if "songid" in request.args:
        try:
            songid = int(request.args["songid"])
        except ValueError:
            # Invalid song id - file not found
            app.logger.warning(f"Failed song edit - {session['username']} - invalid song ID {request.args['songid']}")
            abort(404)

        try:
            song = songs.Song.by_id(songid)
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
            song = songs.Song.by_id(songid)
            if song.userid != userid:
                abort(404)

            return render_template(
                    "song.html",
                    songs=[song],
                    song=song,
                    **users.get_user_colors(userid))
        except ValueError:
            abort(404)
    else:
        return send_from_directory(datadir.get_user_songs_path(userid), str(songid) + ".mp3")

@app.get("/songs")
def view_songs():
    tag = request.args.get("tag", None)
    user = request.args.get("user", None)

    page_colors = colors.DEFAULT_COLORS
    if user:
        page_colors = users.get_user_colors(user)

    if tag and user:
        page_songs = songs.Song.get_all_for_username_and_tag(user, tag)
    elif tag:
        page_songs = songs.Song.get_all_for_tag(tag)
    elif user:
        page_songs = songs.Song.get_all_for_username(user)
    else:
        page_songs = songs.Song.get_random(50)

    return render_template("songs-by-tag.html", user=user, tag=tag, songs=page_songs, **page_colors)

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
            song = songs.Song.by_threadid(comment["threadid"])
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
    plist_songs = songs.Song.get_for_playlist(playlistid)

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

