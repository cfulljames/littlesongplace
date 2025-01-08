from dataclasses import dataclass
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PosixPath

import bcrypt
import click
from flask import Flask, render_template, request, redirect, g, session, abort, \
        send_from_directory, flash
from werkzeug.utils import secure_filename

################################################################################
# Routes
################################################################################

DATA_DIR = Path(".")

app = Flask(__name__)
app.secret_key = "dev"

@app.route("/")
def index():
    username = session.get("username", None)
    return render_template("index.html", username=username)

@app.get("/signup")
def signup_get():
    return render_template("signup.html")

@app.post("/signup")
def signup_post():
    print(request.form)
    username = request.form["username"]
    password = request.form["password"]
    password_confirm = request.form["password_confirm"]

    error = False
    if not username.isidentifier():
        flash("Username cannot contain special characters", "error")
        error = True
    elif len(username) < 3:
        flash("Username must be at least 3 characters", "error")
        error = True

    elif password != password_confirm:
        flash("Passwords do not match", "error")
        error = True
    elif len(password) < 8:
        flash("Password must be at least 8 characters", "error")
        error = True

    if query_db("select * from users where username = ?", [username], one=True):
        flash(f"Username '{username}' is already taken", "error")
        error = True

    if error:
        return redirect(request.referrer)

    password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    query_db("insert into users (username, password) values (?, ?)", [username, password])
    get_db().commit()

    return render_template("login.html", note="User created.  Sign in to continue")

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
        return redirect("/")

    flash("Invalid username/password", "error")
    return render_template("login.html")

@app.get("/logout")
def logout():
    if "username" in session:
        session.pop("username")
    if "userid" in session:
        session.pop("userid")

    return redirect("/")

@app.get("/users")
def users():
    users = [row["username"] for row in query_db("select username from users")]
    return render_template("users.html", users=users)

@app.get("/users/<profile_username>")
def users_profile(profile_username):
    username = session.get("username", None)

    # Look up user data for current profile
    profile_data = query_db("select * from users where username = ?", [profile_username], one=True)
    if profile_data is None:
        abort(404)

    # Get songs for current profile
    profile_userid = profile_data["userid"]
    profile_songs_data = query_db("select * from songs where userid = ?", [profile_userid])
    tags, collabs = get_tags_and_collabs_for_songs(profile_songs_data)

    return render_template(
            "profile.html",
            name=profile_username,
            username=username,
            songs=profile_songs_data,
            songs_tags=tags,
            songs_collaborators=collabs)

@app.get("/edit-song/<int:songid>")
def edit_song(songid=None):
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    if songid:
        try:
            song = Song.from_db(songid)
        except ValueError:
            abort(404)

        return render_template("edit-song.html", song=song)


@app.post("/upload-song/<int:songid>")
def upload_song(songid=None):
    if not "userid" in session:
        return redirect("/login")  # Must be logged in to edit

    error = validate_song_form()

    if not error:
        userid = session["userid"]
        if songid:
            error = update_song(file, userid, title, description, tags, collaborators, songid)
        else:
            error = create_song(file, userid, title, description, tags, collaborators)

    if not error:
        username = session["username"]
        return redirect("/users/{username}")

    else:
        return redirect(request.referrer)

def validate_song_form():
    file = request.files["song"]
    title = request.form["title"]
    description = request.form["description"]

    error = False

    # Check if title is valid
    if not title.isprintable():
        flash(f"'{title}' is not a valid song title", "error")
        error = True

    # Check if description is valid
    if not description.isprintable():
        flash(f"Description contains invalid characters", "error")
        error = True

    # Check if tags are valid
    tags = request.form["tags"]
    tags = [t.strip() for t in tags.split(",")]
    for tag in tags:
        if not tag.isprintable():
            flash(f"'{tag}' is not a valid tag name", "error")
            error = True

    # Check if collaborators are valid
    collaborators = request.form["collabs"]
    collaborators = [c.strip() for c in collaborators.split(",")]
    for collab in collaborators:
        if not collab.isprintable():
            flash(f"'{collab}' is not a valid collaborator name", "error")
            error = True

    return error

def get_user_path(userid):
    userpath = DATA_DIR / "songs" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def update_song(file, userid, title, description, tags, collaborators):
    songid = request.args["songid"]
    try:
        int(songid)
    except ValueError:
        abort(400)

    # Make sure song exists and the logged-in user owns it
    song_data = query_db("select userid from songs where songid = ?", [songid], one=True)
    if song_data is None:
        abort(400)
    elif userid != song_data["userid"]:
        abort(401)

    if file:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            file.save(tmp_file)
            tmp_file.close()

            result = subprocess.run(["mpck", tmp_file.name], stdout=subprocess.PIPE)
            lines = result.stdout.decode().split("\r\n")
            lines = [l.strip().lower() for l in lines]
            passed = any(l.startswith("result") and l.endswith("ok") for l in lines)

            if passed:
                # Move file to permanent location
                shutil.move(tmp_file.name, filepath)
            else:
                flash("Invalid mp3 file", "error")
                error = True

    if not error:
        # Update songs table
        query_db(
                "update songs set userid = ?, title = ?, description = ? where songid = ?",
                [userid, title, description, songid])

        # Update song_tags table
        query_db("delete from song_tags where songid = ?", [songid])
        for tag in tags:
            query_db("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

        # Update song_collaborators table
        query_db("delete from song_collaborators where songid = ?", [songid])
        for collab in collaborators:
            query_db("insert into song_collaborators (name, songid) values (?, ?)", [collab, songid])

        get_db().commit()
        flash(f"Successfully updated '{title}'", "success")

def create_song(file, userid, title, description, tags, collaborators):
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        file.save(tmp_file)
        tmp_file.close()

        result = subprocess.run(["mpck", tmp_file.name], stdout=subprocess.PIPE)
        lines = result.stdout.decode().split("\r\n")
        lines = [l.strip().lower() for l in lines]
        passed = any(l.startswith("result") and l.endswith("ok") for l in lines)

        if not passed:
            flash("Invalid mp3 file", "error")
        else:
            # Create song
            song_data = query_db(
                    "insert into songs (userid, title, description) values (?, ?, ?) returning (songid)",
                    [userid, title, description], one=True)
            songid = song_data["songid"]
            filepath = get_user_path() / (str(song_data["songid"]) + ".mp3")

            # Move file to permanent location
            shutil.move(tmp_file.name, filepath)

            # Assign tags
            for tag in tags:
                query_db("insert into song_tags (tag, songid) values (?, ?)", [tag, songid])

            # Assign collaborators
            for collab in collaborators:
                query_db("insert into song_collaborators (songid, name) values (?, ?)", [songid, collab])

            get_db().commit()

            flash(f"Successfully uploaded '{title}'", "success")

@app.get("/delete-song/<userid>/<songid>")
def delete_song(userid, songid):
    try:
        # Make sure values are valid integers
        int(userid)
        int(songid)
    except ValueError:
        abort(404)

    # Users can only delete their own songs
    if int(userid) != session["userid"]:
        abort(401)

    if not query_db("select * from songs where songid = ?", [songid]):
        abort(404)  # Song doesn't exist

    # Delete tags, collaborators
    query_db("delete from song_tags where songid = ?", [songid])
    query_db("delete from song_collaborators where songid = ?", [songid])

    # Delete song database entry
    query_db("delete from songs where songid = ?", [songid])
    get_db().commit()

    # Delete song file from disk
    songpath = DATA_DIR / "songs" / userid / (songid + ".mp3")
    if songpath.exists():
        os.remove(songpath)

    return redirect(request.referrer)

@app.get("/song/<userid>/<songid>")
def song(userid, songid):
    try:
        # Make sure values are valid integers
        int(userid)
        int(songid)
    except ValueError:
        abort(404)

    return send_from_directory(DATA_DIR / "songs" / userid, songid + ".mp3")

@app.get("/songs-by-tag/<tag>")
def songs_by_tag(tag):
    songs_data = query_db("select * from song_tags inner join songs on song_tags.songid = songs.songid where tag = ?", [tag])
    tags, collabs = get_tags_and_collabs_for_songs(songs_data)

    return render_template(
            "songs-by-tag.html",
            tag=tag,
            username=session["username"],
            songs=songs_data,
            songs_tags=tags,
            songs_collaborators=collabs)

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

def get_tags_and_collabs_for_songs(songs):
    tags = {}
    collabs = {}
    for song in songs:
        songid = song["songid"]
        tags[songid] = query_db("select (tag) from song_tags where songid = ?", [songid])
        collabs[songid] = query_db("select (name) from song_collaborators where songid = ?", [songid])
    return tags, collabs

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
    id: int
    title: str
    description: str
    tags: list[str]
    collaborators: list[str]

    @classmethod
    def from_db(cls, songid):
        song_data = query_db("select * from songs where songid = ?", [songid], one=True)
        if song_data is None:
            raise ValueError(f"No song for ID {songid:d}")

        tags_data = query_db("select * from song_tags where songid = ?", [songid])
        collaborators_data = query_db("select * from song_collaborators where songid = ?", [song])

        tags = [t["tag"] for t in tags_data]
        collabs = [c["name"] for c in collaborators_data]

        return cls(song_data["songid"], song_data["title"], song_data["description"], tags, collabs)

