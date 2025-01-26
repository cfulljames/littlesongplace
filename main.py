import json
import logging
import os
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
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

DATA_DIR = Path(os.environ["DATA_DIR"]) if "DATA_DIR" in os.environ else Path(".")

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
    users = [row["username"] for row in query_db("select username from users order by username asc")]
    songs = Song.get_latest(50)
    song_list = render_template("song-list.html", songs=songs)
    return render_template("index.html", users=users, song_list=song_list)

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
    username = session.get("username", None)

    # Look up user data for current profile
    profile_data = query_db("select * from users where username = ?", [profile_username], one=True)
    if profile_data is None:
        abort(404)

    # Get songs for current profile
    profile_userid = profile_data["userid"]
    songs = Song.get_all_for_userid(profile_userid)

    # Sanitize bio
    profile_bio = ""
    if profile_data["bio"] is not None:
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
        profile_bio = bleach.clean(
                profile_data["bio"],
                tags=allowed_tags,
                attributes=allowed_attributes,
                css_sanitizer=css_sanitizer)

    return render_template(
            "profile.html",
            name=profile_username,
            userid=profile_userid,
            bio=profile_bio,
            song_list=render_template("song-list.html", songs=songs))

@app.post("/update-bio")
def update_bio():
    query_db(
            "update users set bio = ? where userid = ?",
            [request.form["bio"], session["userid"]])
    get_db().commit()
    flash("Bio updated successfully")

    app.logger.info(f"{session['username']} updated bio")

    return redirect(f"/users/{session['username']}")

@app.get("/edit-song")
def edit_song():
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    song = None

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

    return render_template("edit-song.html", song=song)

@app.post("/upload-song")
def upload_song():
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    error = validate_song_form()

    if not error:
        userid = session["userid"]
        if "songid" in request.args:
            error = update_song()
        else:
            error = create_song()

    if not error:
        username = session["username"]
        app.logger.info(f"{username} uploaded/modified a song")
        return redirect(f"/users/{username}")

    else:
        username = session["username"]
        app.logger.info(f"Failed song update - {username}")
        return redirect(request.referrer)

def validate_song_form():
    file = request.files["song"]
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

def get_user_path(userid):
    userpath = DATA_DIR / "songs" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def update_song():
    songid = request.args["songid"]
    try:
        int(songid)
    except ValueError:
        abort(400)

    file = request.files["song"]
    title = request.form["title"]
    description = request.form["description"]
    tags = [t.strip().lower() for t in request.form["tags"].split(",")]
    collaborators = [c.strip() for c in request.form["collabs"].split(",")]

    # Make sure song exists and the logged-in user owns it
    song_data = query_db("select * from songs where songid = ?", [songid], one=True)
    if song_data is None:
        abort(400)
    elif session["userid"] != song_data["userid"]:
        abort(401)

    error = False
    if file:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            passed = convert_song(tmp_file, file)

            if passed:
                # Move file to permanent location
                filepath = get_user_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")
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
    file = request.files["song"]
    title = request.form["title"]
    description = request.form["description"]
    tags = [t.strip() for t in request.form["tags"].split(",")]
    collaborators = [c.strip() for c in request.form["collabs"].split(",")]

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        passed = convert_song(tmp_file, file)

        if not passed:
            return True
        else:
            # Create song
            timestamp = datetime.now(timezone.utc).isoformat()
            song_data = query_db(
                    "insert into songs (userid, title, description, created) values (?, ?, ?, ?) returning (songid)",
                    [session["userid"], title, description, timestamp], one=True)
            songid = song_data["songid"]
            filepath = get_user_path(session["userid"]) / (str(song_data["songid"]) + ".mp3")

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

def convert_song(tmp_file, request_file):
    request_file.save(tmp_file)
    tmp_file.close()

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

    return redirect(request.referrer)

@app.get("/song/<int:userid>/<int:songid>")
def song(userid, songid):
    if request.args.get("action", None) == "view":
        try:
            song = Song.by_id(songid)
            if song.userid != userid:
                abort(404)

            return render_template(
                    "song.html",
                    song_list=render_template("song-list.html", songs=[song]), song=song)
        except ValueError:
            abort(404)
    else:
        return send_from_directory(DATA_DIR / "songs" / str(userid), str(songid) + ".mp3")

@app.get("/songs")
def songs():
    tag = request.args.get("tag", None)
    user = request.args.get("user", None)

    if tag and user:
        songs = Song.get_all_for_username_and_tag(user, tag)
    elif tag:
        songs = Song.get_all_for_tag(tag)
    elif user:
        songs = Song.get_all_for_username(user)
    else:
        songs = []

    return render_template(
            "songs-by-tag.html",
            user=user,
            tag=tag,
            song_list=render_template("song-list.html", songs=songs))

@app.get("/comment")
def comment_get():
    if not "songid" in request.args:
        abort(400) # Must have songid

    try:
        song = Song.by_id(request.args["songid"])
    except ValueError:
        abort(404) # Invald songid

    if not "userid" in session:
        abort(401) # Must be logged in

    comment = None
    if "replytoid" in request.args:
        replytoid = request.args["replytoid"]
        comment = query_db("select * from song_comments inner join users on song_comments.userid == users.userid where commentid = ?", [replytoid], one=True)

    session["previous_page"] = request.referrer
    return render_template("comment.html", song=song, comment=comment)

@app.post("/comment")
def comment_post():
    if not "songid" in request.args:
        abort(400) # Must have songid

    try:
        song = Song.by_id(request.args["songid"])
    except ValueError:
        abort(404) # Invald songid

    comment = None
    if "replytoid" in request.args:
        replytoid = request.args["replytoid"]
        comment = query_db("select * from song_comments inner join users on song_comments.userid == users.userid where commentid = ?", [replytoid], one=True)
        if not comment:
            abort(404) # Invalid comment

    if not "userid" in session:
        abort(401) # Must be logged in

    # Add new comment
    timestamp = datetime.now(timezone.utc).isoformat()
    content = request.form["content"]
    userid = session["userid"]
    songid = request.args["songid"]
    replytoid = request.args.get("replytoid", None)
    query_db(
            "insert into song_comments (songid, userid, replytoid, created, content) values (?, ?, ?, ?, ?)",
            args=[songid, userid, replytoid, timestamp, content])
    get_db().commit()

    if "previous_page" in session:
        return redirect(session["previous_page"])
    else:
        return redirect("/")

@app.get("/site-news")
def site_news():
    return render_template("news.html")

def flash_and_log(msg, category=None):
    flash(msg, category)
    username = session["username"] if "username" in session else "N/A"
    url = request.referrer
    logmsg = f"[{category}] User: {username}, URL: {url} - {msg}"
    if category == "error":
        app.logger.warning(logmsg)
    else:
        app.logger.info(logmsg)

################################################################################
# Database
################################################################################

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATA_DIR / "database.db")
        db.row_factory = sqlite3.Row
    return db

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
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
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

@dataclass
class Song:
    songid: int
    userid: int
    username: str
    title: str
    description: str
    tags: list[str]
    collaborators: list[str]

    def json(self):
        return json.dumps(vars(self))

    def get_comments(self):
        comments = query_db("select * from song_comments inner join users on song_comments.userid == users.userid where songid = ?", [self.songid])
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
    def _from_db(cls, query, args=()):
        songs_data = query_db(query, args)
        tags, collabs = cls._get_info_for_songs(songs_data)
        songs = []
        for sd in songs_data:
            song_tags = [t["tag"] for t in tags[sd["songid"]]]
            song_collabs = [c["name"] for c in collabs[sd["songid"]]]
            songs.append(cls(sd["songid"], sd["userid"], sd["username"], sd["title"], sd["description"], song_tags, song_collabs))

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

