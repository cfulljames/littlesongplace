import os
import sqlite3
import sys
import uuid
from pathlib import Path, PosixPath

import bcrypt
import click
from flask import Flask, render_template, request, redirect, g, session, abort, \
        send_from_directory
from werkzeug.utils import secure_filename

################################################################################
# Check for Required Environment Variables
################################################################################

REQUIRED_VARS = ["SECRET_KEY", "DATA_DIR"]

for var in REQUIRED_VARS:
    if var not in os.environ:
        print(f"{var} not set")
        sys.exit(1)

DATA_DIR = Path(os.environ["DATA_DIR"])

################################################################################
# Routes
################################################################################

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

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

    error = None
    if not username.isalnum():
        error = "Username cannot contain special characters"
    elif len(username) < 3:
        error ="Username must be at least 3 characters"

    elif password != password_confirm:
        error = "Passwords do not match"
    elif len(password) < 8:
        error = "Password must be at least 8 characters"

    if query_db("select * from users where username = ?", [username], one=True):
        error = f"Username '{username}' is already taken"

    if error:
        return render_template("signup.html", error=error)

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

    return render_template("login.html", error="Invalid username/password")

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

    return render_template("profile.html", name=profile_username, username=username, songs=profile_songs_data)

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

    # TODO: Validate song file

    song_data = query_db(
            "insert into songs (userid, title, description) values (?, ?, ?) returning (songid)",
            [userid, title, description], one=True)
    get_db().commit()

    filepath = userpath / (str(song_data["songid"]) + ".mp3")
    file.save(filepath)

    return redirect(f"/users/{username}")

@app.get("/song/<userid>/<songid>")
def song(userid, songid):
    try:
        int(userid) # Make sure userid is a valid integer
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

@click.command("gen-key")
def gen_key():
    """Generate a secret key for session cookie encryption"""
    import secrets
    print(secrets.token_hex())


################################################################################
# App Configuration
################################################################################

app.teardown_appcontext(close_db)
app.cli.add_command(init_db)
app.cli.add_command(gen_key)

