import functools
from datetime import datetime, timezone

import bcrypt
from flask import Blueprint, render_template, redirect, flash, g, request, current_app, session

from . import comments, db
from .logutils import flash_and_log

bp = Blueprint("auth", __name__)

@bp.get("/signup")
def signup_get():
    return render_template("signup.html")

@bp.post("/signup")
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

    if db.query("select * from users where username = ?", [username], one=True):
        flash_and_log(f"Username '{username}' is already taken", "error")
        error = True

    if error:
        current_app.logger.info("Failed signup attempt")
        return redirect(request.referrer)

    password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    timestamp = datetime.now(timezone.utc).isoformat()

    user_data = db.query(
            """
            insert into users (username, password, created)
            values (?, ?, ?)
            returning userid
            """,
            [username, password, timestamp],
            one=True)

    # Create profile comment thread
    threadid = comments.create_thread(comments.ThreadType.PROFILE, user_data["userid"])
    db.query("update users set threadid = ? where userid = ?", [threadid, user_data["userid"]])
    db.commit()

    flash("User created.  Please sign in to continue.", "success")
    current_app.logger.info(f"Created user {username}")

    return redirect("/login")

@bp.get("/login")
def login_get():
    return render_template("login.html")

@bp.post("/login")
def login_post():
    username = request.form["username"]
    password = request.form["password"]

    user_data = db.query("select * from users where username = ?", [username], one=True)

    if user_data and bcrypt.checkpw(password.encode(), user_data["password"]):
        # Successful login
        session["username"] = username
        session["userid"] = user_data["userid"]
        session.permanent = True
        current_app.logger.info(f"{username} logged in")

        return redirect(f"/users/{username}")

    flash("Invalid username/password", "error")
    current_app.logger.info(f"Failed login for {username}")

    return render_template("login.html")


@bp.get("/logout")
def logout():
    if "username" in session:
        session.pop("username")
    if "userid" in session:
        session.pop("userid")

    return redirect("/")

def requires_login(f):
    @functools.wraps(f)
    def _wrapper(*args, **kwargs):
        if not "userid" in session:
            return redirect("/login")

        g.userid = session["userid"]
        g.username = session["username"]

        return f(*args, **kwargs)

    return _wrapper

