import enum
from datetime import datetime, timezone

from flask import abort, Blueprint, g, redirect, render_template, request, session

from . import auth, db, push_notifications, songs
from .sanitize import sanitize_user_text

bp = Blueprint("comments", __name__)

class ThreadType(enum.IntEnum):
    SONG = 0
    PROFILE = 1
    PLAYLIST = 2
    JAM_EVENT = 3

class ObjectType(enum.IntEnum):
    COMMENT = 0

def create_thread(threadtype, userid):
    thread = db.query(
            """
            insert into comment_threads (threadtype, userid)
            values (?, ?)
            returning threadid
            """,
            [threadtype, userid],
            one=True)
    db.commit()
    return thread["threadid"]

def for_thread(threadid):
    thread_comments = db.query(
            """
            select * from comments
            inner join users on comments.userid == users.userid
            where comments.threadid = ?
            """,
            [threadid])
    thread_comments = [dict(c) for c in thread_comments]
    for c in thread_comments:
        c["content"] = sanitize_user_text(c["content"])

    # Top-level comments
    song_comments = sorted(
            [dict(c) for c in thread_comments if c["replytoid"] is None],
            key=lambda c: c["created"])
    song_comments = list(reversed(song_comments))
    # Replies (can only reply to top-level)
    for comment in song_comments:
        comment["replies"] = sorted(
                [c for c in thread_comments if c["replytoid"] == comment["commentid"]],
                key=lambda c: c["created"])

    return song_comments

@bp.route("/comment", methods=["GET", "POST"])
@auth.requires_login
def comment():
    if not "threadid" in request.args:
        abort(400) # Must have threadid

    thread = db.query(
            """
            select * from comment_threads
            where threadid = ?
            """,
            [request.args["threadid"]],
            one=True)
    if not thread:
        abort(404) # Invalid threadid

    # Check for comment being replied to
    replyto = None
    if "replytoid" in request.args:
        replytoid = request.args["replytoid"]
        replyto = db.query(
                """
                select * from comments
                inner join users on comments.userid == users.userid
                where commentid = ?
                """,
                [replytoid],
                one=True)
        if not replyto:
            abort(404) # Invalid comment

    # Check for comment being edited
    comment = None
    if "commentid" in request.args:
        commentid = request.args["commentid"]
        comment = db.query(
                """
                select * from comments
                inner join users on comments.userid == users.userid
                where commentid = ?
                """,
                [commentid],
                one=True)
        if not comment:
            abort(404) # Invalid comment
        if comment["userid"] != session["userid"]:
            abort(403) # User doesn't own this comment

    if request.method == "GET":
        # Show the comment editor
        session["previous_page"] = request.referrer
        threadtype = thread["threadtype"]
        song = None
        profile = None
        playlist = None
        if threadtype == ThreadType.SONG:
            song = songs.by_threadid(request.args["threadid"])
        elif threadtype == ThreadType.PROFILE:
            profile = db.query(
                    "select * from users where threadid = ?",
                    [request.args["threadid"]],
                    one=True)
        elif threadtype == ThreadType.PLAYLIST:
            profile = db.query(
                    """
                    select * from playlists
                    inner join users on playlists.userid = users.userid
                    where playlists.threadid = ?
                    """,
                    [request.args["threadid"]],
                    one=True)
        return render_template(
            "comment.html",
            song=song,
            profile=profile,
            playlist=playlist,
            replyto=replyto,
            comment=comment,
        )

    elif request.method == "POST":
        # Add/update comment (user clicked the Post Comment button)
        content = request.form["content"]
        if comment:
            # Update existing comment
            db.query(
                    "update comments set content = ? where commentid = ?",
                    args=[content, comment["commentid"]])
        else:
            # Add new comment
            timestamp = datetime.now(timezone.utc).isoformat()
            userid = session["userid"]
            replytoid = request.args.get("replytoid", None)

            threadid = request.args["threadid"]
            comment = db.query(
                    """
                    insert into comments
                        (threadid, userid, replytoid, created, content)
                    values (?, ?, ?, ?, ?)
                    returning (commentid)
                    """,
                    args=[threadid, userid, replytoid, timestamp, content],
                    one=True)
            commentid = comment["commentid"]

            # Notify content owner
            notification_targets = {thread["userid"]}
            if replyto:
                # Notify parent commenter
                notification_targets.add(replyto["userid"])

                # Notify previous repliers in thread
                previous_replies = db.query(
                        "select * from comments where replytoid = ?", [replytoid])
                for reply in previous_replies:
                    notification_targets.add(reply["userid"])

            # Don't notify the person who wrote the comment
            if userid in notification_targets:
                notification_targets.remove(userid)

            # Create notifications in database
            for target in notification_targets:
                db.query(
                        """
                        insert into notifications
                            (objectid, objecttype, targetuserid, created)
                        values (?, ?, ?, ?)
                        """,
                        [commentid, ObjectType.COMMENT, target, timestamp])

            # Send push notifications
            push_notifications.notify(
                    notification_targets,
                    title=f"Comment from {g.username}",
                    body=content,
                    url="/activity",
                    setting=push_notifications.SubscriptionSetting.COMMENTS)

        db.commit()

        return redirect_to_previous_page()

def redirect_to_previous_page():
    previous_page = "/"
    if "previous_page" in session:
        previous_page = session["previous_page"]
        session.pop("previous_page")
    return redirect(previous_page)

@bp.get("/delete-comment/<int:commentid>")
def comment_delete(commentid):
    if "userid" not in session:
        return redirect("/login")

    comment = db.query(
            """
            select c.userid as comment_user, t.userid as thread_user
            from comments as c
            inner join comment_threads as t
            on c.threadid == t.threadid
            where commentid = ?
            """,
            [commentid],
            one=True)
    if not comment:
        abort(404) # Invalid comment

    # Only commenter and song owner can delete comments
    if not ((comment["comment_user"] == session["userid"])
            or (comment["thread_user"] == session["userid"])):
        abort(403)

    db.query(
            "delete from comments where (commentid = ?) or (replytoid = ?)",
            [commentid, commentid])
    db.commit()

    return redirect(request.referrer)

