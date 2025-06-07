from datetime import datetime, timezone

from flask import abort, Blueprint, get_flashed_messages, session, redirect, \
        render_template, request

from . import comments, db, songs, users
from .logutils import flash_and_log

bp = Blueprint("playlists", __name__)

@bp.post("/create-playlist")
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
        """
        insert into playlists (created, updated, userid, name, private, threadid)
        values (?, ?, ?, ?, ?, ?)
        """,
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

@bp.get("/delete-playlist/<int:playlistid>")
def delete_playlist(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = db.query(
            "select * from playlists where playlistid = ?",
            args=[playlistid],
            one=True)
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

@bp.post("/append-to-playlist")
def append_to_playlist():
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    try:
        playlistid = int(request.form["playlistid"])
    except ValueError:
        abort(400)

    plist_data = db.query(
            "select * from playlists where playlistid = ?",
            args=[playlistid],
            one=True)
    if not plist_data:
        abort(404)

    # Cannot edit other user's playlist
    if session["userid"] != plist_data["userid"]:
        abort(403)

    songid = request.form["songid"]

    # Make sure song exists
    song_data = db.query(
            "select * from songs where songid = ?",
            args=[songid],
            one=True)
    if not song_data:
        abort(404)

    # Set index to one more than the current max
    existing_songs = db.query(
            "select * from playlist_songs where playlistid = ?",
            args=[playlistid])
    if existing_songs:
        new_position = max(s["position"] for s in existing_songs) + 1
    else:
        new_position = 1

    # Add to playlist
    db.query(
            """
            insert into playlist_songs (playlistid, position, songid)
            values (?, ?, ?)
            """,
            args=[playlistid, new_position, songid])

    # Update modification time
    timestamp = datetime.now(timezone.utc).isoformat()
    db.query(
            "update playlists set updated = ? where playlistid = ?",
            args=[timestamp, playlistid])
    db.commit()

    flash_and_log(
            f"Added '{song_data['title']}' to {plist_data['name']}",
            "success")

    return {"status": "success", "messages": get_flashed_messages()}

@bp.post("/edit-playlist/<int:playlistid>")
def edit_playlist_post(playlistid):
    if not "userid" in session:
        abort(401)

    # Make sure playlist exists
    plist_data = db.query(
            "select * from playlists where playlistid = ?",
            args=[playlistid],
            one=True)
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
            song_data = db.query(
                    "select * from songs where songid = ?", args=[songid])
            if not song_data:
                abort(400)

    # All songs valid - delete old songs
    db.query("delete from playlist_songs where playlistid = ?", args=[playlistid])

    # Re-add songs with new positions
    for position, songid in enumerate(songids):
        print(position, songid)
        db.query(
                """
                insert into playlist_songs (playlistid, position, songid)
                values (?, ?, ?)
                """,
                args=[playlistid, position, songid])

    # Update private, name
    private = int(request.form["type"] == "private")
    db.query(
            "update playlists set private = ?, name = ? where playlistid = ?",
            [private, name, playlistid])

    db.commit()

    flash_and_log("Playlist updated", "success")
    return redirect(request.referrer)

@bp.get("/playlists/<int:playlistid>")
def playlists(playlistid):

    # Make sure playlist exists
    plist_data = db.query(
            """
            select * from playlists
            inner join users on playlists.userid = users.userid
            where playlistid = ?
            """,
            args=[playlistid],
            one=True)
    if not plist_data:
        abort(404)

    # Protect private playlists
    if plist_data["private"]:
        if ("userid" not in session) or (session["userid"] != plist_data["userid"]):
            # Cannot view other user's private playlist - pretend it doesn't even exist
            abort(404)

    # Get songs
    plist_songs = songs.get_for_playlist(playlistid)

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
