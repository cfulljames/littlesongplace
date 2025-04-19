from datetime import datetime, timezone

from flask import Blueprint, redirect, render_template, session

from . import comments, db, songs

bp = Blueprint("activity", __name__)

@bp.get("/activity")
def activity():
    if not "userid" in session:
        return redirect("/login")

    # Get comment notifications
    notifications = db.query(
        """
        select
            c.content,
            c.commentid,
            c.replytoid,
            cu.username as comment_username,
            rc.content as replyto_content,
            c.threadid,
            t.threadtype
        from notifications as n
        inner join comments as c on n.objectid == c.commentid
        inner join comment_threads as t on c.threadid = t.threadid
        left join comments as rc on c.replytoid == rc.commentid
        inner join users as cu on cu.userid == c.userid
        where (n.targetuserid = ?) and (n.objecttype = ?)
        order by c.created desc
        """,
        [session["userid"], comments.ObjectType.COMMENT])

    notifications = [dict(c) for c in notifications]
    for comment in notifications:
        threadtype = comment["threadtype"]
        if threadtype == comments.ThreadType.SONG:
            song = songs.by_threadid(comment["threadid"])
            comment["songid"] = song.songid
            comment["title"] = song.title
            comment["content_userid"] = song.userid
            comment["content_username"] = song.username
        elif threadtype == comments.ThreadType.PROFILE:
            profile = db.query(
                    "select * from users where threadid = ?",
                    [comment["threadid"]],
                    one=True)
            comment["content_userid"] = profile["userid"]
            comment["content_username"] = profile["username"]
        elif threadtype == comments.ThreadType.PLAYLIST:
            playlist = db.query(
                """\
                select * from playlists
                inner join users on playlists.userid == users.userid
                where playlists.threadid = ?
                """,
                [comment["threadid"]],
                one=True,
            )
            comment["playlistid"] = playlist["playlistid"]
            comment["name"] = playlist["name"]
            comment["content_userid"] = playlist["userid"]
            comment["content_username"] = playlist["username"]
        elif threadtype == comments.ThreadType.JAM_EVENT:
            jam_event = db.query(
                    """\
                    SELECT * FROM jam_events
                    INNER JOIN jams ON jam_events.jamid = jams.jamid
                    INNER JOIN users ON jams.ownerid = users.userid
                    WHERE jam_events.threadid = ?
                    """, [comment["threadid"]], one=True)
            comment["eventid"] = jam_event["eventid"]
            comment["jamid"] = jam_event["jamid"]
            comment["title"] = jam_event["title"]
            comment["content_userid"] = jam_event["userid"]
            comment["content_username"] = jam_event["username"]

    timestamp = datetime.now(timezone.utc).isoformat()
    db.query(
            "update users set activitytime = ? where userid = ?",
            [timestamp, session["userid"]])
    db.commit()

    return render_template("activity.html", comments=notifications)

@bp.get("/new-activity")
def new_activity():
    has_new_activity = False
    if "userid" in session:
        user_data = db.query(
                "select activitytime from users where userid = ?",
                [session["userid"]],
                one=True)
        comment_data = db.query(
            """\
            select created from notifications
            where targetuserid = ?
            order by created desc
            limit 1
            """,
            [session["userid"]],
            one=True)

        if comment_data:
            comment_time = comment_data["created"]
            last_checked = user_data["activitytime"]

            if (last_checked is None) or (last_checked < comment_time):
                has_new_activity = True

    return {"new_activity": has_new_activity}

