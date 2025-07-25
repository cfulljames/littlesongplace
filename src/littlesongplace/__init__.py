import base64
import logging
import os
import random
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click
from flask import Flask, render_template, request, redirect, g, session, abort, \
        send_from_directory, flash, get_flashed_messages
from werkzeug.middleware.proxy_fix import ProxyFix

from . import activity, auth, colors, comments, datadir, db, jams, playlists, \
        profiles, songs, users
from .logutils import flash_and_log

# Logging

handler = RotatingFileHandler(datadir.get_app_log_path(), maxBytes=1_000_000, backupCount=10)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))

root_logger = logging.getLogger()
root_logger.addHandler(handler)

# Flask app

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"] if "SECRET_KEY" in os.environ else "dev"
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024 * 1024
app.register_blueprint(activity.bp)
app.register_blueprint(auth.bp)
app.register_blueprint(comments.bp)
app.register_blueprint(jams.bp)
app.register_blueprint(playlists.bp)
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
    start = time.perf_counter()
    all_users = db.query("select * from users order by username asc")
    all_users = [dict(row) for row in all_users]
    for user in all_users:
        user["has_pfp"] = users.user_has_pfp(user["userid"])
        for key, value in users.get_user_colors(user).items():
            user[key] = value
    app.logger.info(f"Homepage users in {time.perf_counter() - start} seconds")

    titles = [
            ("Little Song Place", 2.0),
            ("Lumpy Space Princess", 0.2),
            ("Language Server Protocol", 0.1),
            ("Liskov Substitution Principle", 0.1),
    ]
    titles, weights = zip(*titles)
    title = random.choices(titles, weights)[0]

    start = time.perf_counter()
    rows = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            """)
    all_jams = [jams.Jam.from_row(r) for r in rows]
    all_events = []
    for j in all_jams:
        all_events.extend(j.events)
    ongoing_events, upcoming_events, _, _ = jams._sort_events(all_events)
    app.logger.info(f"Homepage jams in {time.perf_counter() - start} seconds")

    # Group songs by userid
    start = time.perf_counter()
    page_songs = songs.get_latest(100)
    songs_by_user = []
    prev_song_user = None
    for song in page_songs:
        if not song.hidden:  # Don't show any hidden songs on homepage
            if song.userid != prev_song_user:
                songs_by_user.append([])
                prev_song_user = song.userid
            songs_by_user[-1].append(song)
    app.logger.info(f"Homepage songs in {time.perf_counter() - start} seconds")

    start = time.perf_counter()
    page = render_template(
            "index.html",
            users=all_users,
            songs_by_user=songs_by_user,
            page_title=title,
            ongoing_events=ongoing_events,
            upcoming_events=upcoming_events)
    app.logger.info(f"Homepage render in {time.perf_counter() - start} seconds")

    return page

@app.get("/site-news")
def site_news():
    return render_template("news.html")

@app.get("/about")
def about():
    return render_template("about.html")

def get_gif_data():
    # Convert all .gifs to base64 strings and embed them as dataset entries
    # in <div>s.  This is used by nav.js:customImage() - it replaces specific
    # bytes in the .gif data to swap the color palette, avoiding the need to
    # do a pixel-by-pixel filter in the javascript.  Is it actually any faster?
    # I have no idea.
    gifs = []
    static_path = Path(__file__).parent / "static"
    for child in static_path.iterdir():
        if child.suffix == ".gif":
            with open(child, "rb") as gif:
                b64 = base64.b64encode(gif.read()).decode()
                gifs.append(
                        '<div '
                        'class="img-data" '
                        f'id="{child.stem}" '
                        f'data-img-b64="{b64}"'
                        '></div>')

    gifs = "\n".join(gifs)
    return gifs

def get_current_user_playlists():
    plist_data = []
    if "userid" in session:
        plist_data = db.query(
                "select * from playlists where userid = ?",
                [session["userid"]])

    return plist_data

@app.context_processor
def inject_global_vars():
    return dict(
        gif_data=get_gif_data(),
        # Add to Playlist dropdown entries
        current_user_playlists=get_current_user_playlists(),
        **colors.DEFAULT_COLORS,
    )

@app.cli.add_command
@click.command("gen-key")
def gen_key():
    """Generate a secret key for session cookie encryption"""
    import secrets
    print(secrets.token_hex())

