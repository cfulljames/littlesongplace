import json
import os
import random
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from flask import Blueprint, current_app, g, render_template, request, redirect, \
        session, abort, send_from_directory
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import auth, comments, colors, datadir, db, push_notifications, users
from .sanitize import sanitize_user_text
from .logutils import flash_and_log

bp = Blueprint("songs", __name__)

@dataclass
class Song:
    songid: int
    userid: int
    user: users.User
    threadid: int
    username: str
    title: str
    description: str
    created: str
    tags: list[str]
    collaborators: list[str]
    user_has_pfp: bool
    hidden: bool
    eventid: Optional[int]
    jamid: Optional[int]
    event_title: Optional[str]

    def json(self):
        vs = vars(self)
        return json.dumps({k: vs[k] for k in vs if not isinstance(vs[k], users.User)})

    def get_comments(self):
        return comments.for_thread(self.threadid)

def by_id(songid):
    songs = _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        where songid = ?
        """,
        [songid])
    if not songs:
        raise ValueError(f"No song for ID {songid:d}")

    return songs[0]

def by_threadid(threadid):
    songs = _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        where songs.threadid = ?
        """,
        [threadid])
    if not songs:
        raise ValueError(f"No song for Thread ID {songid:d}")

    return songs[0]

def get_all_for_userid(userid):
    return _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        where songs.userid = ?
        order by songs.created desc
        """,
        [userid])

def get_all_for_username(username):
    return _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        where users.username = ?
        order by songs.created desc
        """,
        [username])

def get_all_for_username_and_tag(username, tag):
    return _from_db(
        """
        select * from song_tags
        inner join songs on song_tags.songid = songs.songid
        inner join users on songs.userid = users.userid
        where (username = ? and tag = ?)
        order by songs.created desc
        """,
        [username, tag])

def get_all_for_tag(tag):
    return _from_db(
        """
        select * from song_tags
        inner join songs on song_tags.songid = songs.songid
        inner join users on songs.userid = users.userid
        where (tag = ?)
        order by songs.created desc
        """,
        [tag])

def get_latest(count):
    return _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        order by songs.created desc
        limit ?
        """,
        [count])

def get_random(count):
    # Get random songs + 10 extras so I can filter out my own
    # (I uploaded too many :/)
    songs = _from_db(
        """
        select * from songs
        inner join users on songs.userid = users.userid
        where songid in (
            select songid from songs
            order by random()
            limit ?
        )
        """,
        [count + 10])
    random.shuffle(songs)

    # Prevent my songs from showing up in the first 10 results
    for i in reversed(range(min(10, len(songs)))):
        if songs[i].username == "cfulljames":
            del songs[i]

    # Drop any extra songs (since we asked for 10 extras)
    songs = songs[:count]

    return songs

def get_for_playlist(playlistid):
    return _from_db(
        """
        select * from playlist_songs
        inner join songs on playlist_songs.songid = songs.songid
        inner join users on songs.userid = users.userid
        where playlistid = ?
        order by playlist_songs.position asc
        """,
        [playlistid])

def get_for_event(eventid):
    return _from_db(
        """
        SELECT * FROM songs
        INNER JOIN users ON songs.userid = users.userid
        WHERE songs.eventid = ?
        """,
        [eventid])

def _get_song_info_list(table, column, songid):
    rows = db.query(
            f"SELECT ({column}) FROM {table} WHERE songid = ?", [songid])
    return [r[column] for r in rows if r[column]]

def _from_db(query, args=()):
    songs_data = db.query(query, args)
    songs = []
    for sd in songs_data:
        songid = sd["songid"]
        song_tags = _get_song_info_list("song_tags", "tag", songid)
        song_collabs = _get_song_info_list("song_collaborators", "name", songid)

        # Song is hidden if it was submitted to an event that hasn't ended yet
        hidden = False
        jamid = None
        event_title = None

        if sd["eventid"]:
            event_row = db.query(
                    "SELECT * FROM jam_events WHERE eventid = ?",
                    [sd["eventid"]],
                    one=True)
            if event_row:
                jamid = event_row["jamid"]
                event_title = event_row["title"]
                if event_row["enddate"]:
                    enddate = datetime.fromisoformat(event_row["enddate"])
                    hidden = datetime.now(timezone.utc) < enddate


        created = (
                datetime.fromisoformat(sd["created"])
                .strftime("%Y-%m-%d"))

        songs.append(Song(
            songid=sd["songid"],
            userid=sd["userid"],
            user=users.User.from_row(sd),
            threadid=sd["threadid"],
            username=sd["username"],
            title=sd["title"],
            description=sanitize_user_text(sd["description"]),
            created=created,
            tags=song_tags,
            collaborators=song_collabs,
            user_has_pfp=users.user_has_pfp(sd["userid"]),
            hidden=hidden,
            eventid=sd["eventid"],
            jamid=jamid,
            event_title=event_title,
        ))
    return songs

@bp.get("/edit-song")
@auth.requires_login
def edit_song():
    song = None

    song_colors = users.get_user_colors(session["userid"])
    eventid = request.args.get("eventid", None)

    if "songid" in request.args:
        try:
            songid = int(request.args["songid"])
        except ValueError:
            # Invalid song id - file not found
            current_app.logger.warning(
                f"Failed song edit - {session['username']} "
                f"- invalid song ID {request.args['songid']}")
            abort(404)

        try:
            song = by_id(songid)
            if not song.userid == session["userid"]:
                # Can't edit someone else's song - 401 unauthorized
                current_app.logger.warning(
                    f"Failed song edit - {session['username']} "
                    "- attempted update for unowned song")
                abort(401)
        except ValueError:
            # Song doesn't exist - 404 file not found
            current_app.logger.warning(
                f"Failed song edit - {session['username']} "
                f"- song doesn't exist ({songid})")
            abort(404)

    return render_template("edit-song.html", song=song, **song_colors, eventid=eventid)

@bp.post("/upload-song")
@auth.requires_login
def upload_song():
    userid = session["userid"]

    error = validate_song_form()

    if not error:
        if "songid" in request.args:
            error = update_song()
        else:
            error = create_song()

    if not error:
        username = session["username"]
        current_app.logger.info(f"{username} uploaded/modified a song")
        if "songid" in request.args:
            # After editing an existing song, go back to song page
            return redirect(
                f"/song/{userid}/{request.args['songid']}?action=view")
        else:
            # After creating a new song, go back to profile/event page
            if "eventid" in request.args:
                eventid = int(request.args["eventid"])
                evt = db.query(
                        "SELECT * FROM jam_events WHERE eventid = ?",
                        [eventid], one=True)
                jamid = evt["jamid"]
                return redirect(f"/jams/{jamid}/events/{eventid}")
            else:
                return redirect(f"/users/{username}")

    else:
        username = session["username"]
        current_app.logger.info(f"Failed song update - {username}")
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
                user_songs_path = datadir.get_user_songs_path(session["userid"])
                filepath = user_songs_path / (str(song_data["songid"]) + ".mp3")
                shutil.move(tmp_file.name, filepath)
            else:
                error = True

    if not error:
        # Update songs table
        db.query(
            """
            update songs set title = ?, description = ?
            where songid = ?
            """,
            [title, description, songid])

        # Update song_tags table
        db.query("delete from song_tags where songid = ?", [songid])
        for tag in tags:
            db.query(
                """
                insert into song_tags (tag, songid)
                values (?, ?)
                """,
                [tag, songid])

        # Update song_collaborators table
        db.query("delete from song_collaborators where songid = ?", [songid])
        for collab in collaborators:
            db.query(
                """
                insert into song_collaborators (name, songid)
                values (?, ?)
                """,
                [collab, songid])

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
    try:
        eventid = int(request.args["eventid"]) if "eventid" in request.args else None
    except ValueError:
        abort(400)

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        passed = convert_song(tmp_file, file, yt_url)

        if not passed:
            return True
        else:
            # Create comment thread
            threadid = comments.create_thread(
                comments.ThreadType.SONG, session["userid"])

            # Create song
            timestamp = datetime.now(timezone.utc).isoformat()
            song_data = db.query(
                """
                insert into songs (userid, title, description, created, threadid, eventid)
                values (?, ?, ?, ?, ?, ?)
                returning (songid)
                """,
                [session["userid"], title, description, timestamp, threadid, eventid],
                one=True)

            # Move file to permanent location
            user_songs_path = datadir.get_user_songs_path(session["userid"])
            filepath = user_songs_path / (str(song_data["songid"]) + ".mp3")
            shutil.move(tmp_file.name, filepath)

            # Assign tags
            songid = song_data["songid"]
            for tag in tags:
                db.query(
                    "insert into song_tags (tag, songid) values (?, ?)",
                    [tag, songid])

            # Assign collaborators
            for collab in collaborators:
                db.query(
                    "insert into song_collaborators (songid, name) values (?, ?)",
                    [songid, collab])

            db.commit()

            flash_and_log(f"Successfully uploaded '{title}'", "success")

            # Send push notifications to all other users
            push_notifications.notify_all(
                    f"New song from {g.username}", title, _except=g.userid)

            return False  # No error

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
            current_app.logger.warning(str(ex))
            flash_and_log(f"Failed to import from YouTube URL: {yt_url}")
            return False

    result = subprocess.run(["mpck", tmp_file.name], stdout=subprocess.PIPE)
    res_stdout = result.stdout.decode()
    current_app.logger.info(f"mpck result: \n {res_stdout}")
    lines = res_stdout.split("\n")
    lines = [l.strip().lower() for l in lines]
    if any(l.startswith("result") and l.endswith("ok") for l in lines):
        # Uploaded valid mp3 file
        return True

    # Not a valid mp3, try to convert with ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as out_file:
        out_file.close()
        os.remove(out_file.name)
        result = subprocess.run(
            ["ffmpeg", "-i", tmp_file.name, out_file.name],
            stdout=subprocess.PIPE)
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
        'logger': current_app.logger,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([yt_url])

@bp.get("/delete-song/<int:songid>")
@auth.requires_login
def delete_song(songid):
    song_data = db.query(
        "select * from songs where songid = ?", [songid], one=True)

    if not song_data:
        current_app.logger.warning(
            f"Failed song delete - {session['username']} - song doesn't exist")
        abort(404)  # Song doesn't exist

    # Users can only delete their own songs
    if song_data["userid"] != session["userid"]:
        current_app.logger.warning(
            f"Failed song delete - {session['username']} - user doesn't own song")
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

    current_app.logger.info(
        f"{session['username']} deleted song: {song_data['title']}")
    flash_and_log(f"Deleted '{song_data['title']}'", "success")

    return redirect(f"/users/{session['username']}")

@bp.get("/song/<int:userid>/<int:songid>")
def song(userid, songid):
    if request.args.get("action", None) == "view":
        try:
            song = by_id(songid)
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
        return send_from_directory(
            datadir.get_user_songs_path(userid), str(songid) + ".mp3")

@bp.get("/songs")
def view_songs():
    tag = request.args.get("tag", None)
    user = request.args.get("user", None)

    page_colors = colors.DEFAULT_COLORS
    if user:
        page_colors = users.get_user_colors(user)

    if tag and user:
        page_songs = get_all_for_username_and_tag(user, tag)
    elif tag:
        page_songs = get_all_for_tag(tag)
    elif user:
        page_songs = get_all_for_username(user)
    else:
        page_songs = get_random(50)

    return render_template(
        "songs-by-tag.html",
        user=user,
        tag=tag,
        songs=page_songs,
        **page_colors)

