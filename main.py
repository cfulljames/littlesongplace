import os
import sqlite3
import uuid
from pathlib import Path, PosixPath

import bcrypt
import click
from flask import Flask, render_template, request, redirect, g, session, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "TODO"

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
        session.permanent = True
        return redirect("/")

    return render_template("login.html", error="Invalid username/password")

@app.get("/logout")
def logout():
    if "username" in session:
        session.pop("username")

    return redirect("/")

@app.get("/users")
def users():
    users = [row["username"] for row in query_db("select username from users")]
    return render_template("users.html", users=users)

@app.get("/users/<name>")
def users_profile(name):
    username = session.get("username", None)
    songsdir = f"static/users/{username}/songs/"
    songspath = Path(f"static/users/{username}/songs")
    songs = []
    if songspath.exists():
        songs = [child.name for child in songspath.iterdir() if child.suffix.lower() == ".mp3"]
        print(songs)
    return render_template("profile.html", name=name, username=username, songs=songs)

@app.post("/uploadsong")
def upload_song():
    if not "username" in session:
        abort(401)

    username = session["username"]
    userpath = Path(f"static/users/{username}/songs")
    if not userpath.exists():
        os.makedirs(userpath)

    file = request.files["song"]
    filename = secure_filename(file.filename)
    filepath = userpath / filename
    file.save(filepath)

    return redirect(f"/users/{username}")


################################################################################
# Database
################################################################################

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect("database.db")
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

app.teardown_appcontext(close_db)
app.cli.add_command(init_db)

