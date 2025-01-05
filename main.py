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
    profile_songs_tags = {}
    profile_songs_collabs = {}
    for song in profile_songs_data:
        songid = song["songid"]
        profile_songs_tags[songid] = query_db("select (tag) from song_tags where songid = ?", [songid])
        profile_songs_collabs[songid] = query_db("select (name) from song_collaborators where songid = ?", [songid])

    return render_template(
            "profile.html",
            name=profile_username,
            username=username,
            songs=profile_songs_data,
            songs_tags=profile_songs_tags,
            songs_collaborators=profile_songs_collabs)

@app.post("/uploadsong")
def upload_song():
    if not "username" in session:
        abort(401)

    username = session["username"]
    userid = session["userid"]
    userpath = DATA_DIR / "songs" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)

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

    # Validate and save mp3 file
    if not error:
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
                filepath = userpath / (str(song_data["songid"]) + ".mp3")

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

