import functools
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import abort, Blueprint, g, redirect, render_template, request, url_for

from . import auth, comments, db
from .sanitize import sanitize_user_text

bp = Blueprint("jams", __name__, url_prefix="/jams")


def jam_owner_only(f):
    @functools.wraps(f)
    def _wrapper(jamid, *args, **kwargs):
        row = db.query(
                "SELECT * FROM jams WHERE jamid = ?", [jamid], expect_one=True)

        if row["ownerid"] != g.userid:
            abort(403)  # Forbidden; cannot modify other user's jam

        return f(jamid, *args, **kwargs)
    return _wrapper

def _sort_events(events):
    now = datetime.now(timezone.utc)
    # Only show events with valid timestamps
    events = [e for e in events if e.startdate and e.enddate]
    ongoing_events = [e for e in events if e.startdate <= now and e.enddate >= now]
    upcoming_events = [e for e in events if e.startdate > now]
    past_events = [e for e in events if e.enddate < now]
    return ongoing_events, upcoming_events, past_events

@bp.get("")
def jams():
    # Show a list of all jams: ongoing, upcoming, previous
    rows = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            """)
    jams = [Jam.from_row(r) for r in rows]

    all_events = []
    for j in jams:
        all_events.extend(j.events)

    # Only show events with valid timestamps
    all_events = [e for e in all_events if e.startdate and e.enddate]

    ongoing_events, upcoming_events, past_events = _sort_events(all_events)
    past_events = past_events[-5:] # Only show 5 most recent events

    # TODO: Sort into groups based on start/end dates
    return render_template(
            "jams-main.html",
            ongoing=ongoing_events,
            upcoming=upcoming_events,
            past=past_events,
            jams=jams)


@bp.get("/create")
@auth.requires_login
def create():
    # Create a new jam and redirect to the edit form
    timestamp = datetime.now(timezone.utc).isoformat()
    row = db.query(
            """
            INSERT INTO jams (ownerid, created, title)
            VALUES (?, ?, ?)
            RETURNING jamid
            """, [g.userid, timestamp, f"New Jam"], one=True)
    db.commit()
    jamid = row["jamid"]
    return redirect(url_for("jams.jam", jamid=jamid))


@bp.get("/<int:jamid>")
def jam(jamid):
    jam = _get_jam_by_id(jamid)
    ongoing_events, upcoming_events, past_events = _sort_events(jam.events)
    # Show the main jam page
    return render_template(
            "jam.html",
            jam=jam,
            ongoing=ongoing_events,
            upcoming=upcoming_events,
            past=past_events)


@bp.post("/<int:jamid>/update")
@auth.requires_login
@jam_owner_only
def update(jamid):
    # Update a jam with the new form data, redirect to view page
    title = request.form["title"]
    description = request.form["description"]
    row = db.query(
            """
            UPDATE jams
            SET title = ?, description = ?
            WHERE jamid = ?
            RETURNING *
            """, [title, description, jamid], expect_one=True)

    db.commit()
    return redirect(url_for("jams.jam", jamid=jamid))


@bp.get("/<int:jamid>/delete")
@auth.requires_login
@jam_owner_only
def delete(jamid):
    # Delete a jam, redirect to the jams list
    row = db.query(
            "DELETE FROM jams WHERE jamid = ? RETURNING *",
            [jamid], expect_one=True)

    db.commit()
    return redirect(url_for("jams.jams"))


@bp.get("/<int:jamid>/events/create")
@auth.requires_login
@jam_owner_only
def events_create(jamid):
    # Create a new event and redirect to the edit form
    threadid = comments.create_thread(comments.ThreadType.JAM_EVENT, g.userid)
    timestamp = datetime.now(timezone.utc).isoformat()
    row = db.query(
            """
            INSERT INTO jam_events (jamid, threadid, created, title)
            VALUES (?, ?, ?, ?)
            RETURNING eventid
            """, [jamid, threadid, timestamp, "New Event"], one=True)
    db.commit()

    eventid = row["eventid"]
    return redirect(url_for("jams.events_view", jamid=jamid, eventid=eventid))


@bp.get("/<int:jamid>/events/<int:eventid>")
def events_view(jamid, eventid):
    # Show the event page
    jam = _get_jam_by_id(jamid)
    try:
        event = next(e for e in jam.events if e.eventid == eventid)
    except StopIteration:
        abort(404)  # No event with this ID

    return render_template("jam-event.html", jam=jam, event=event)


@bp.post("/<int:jamid>/events/<int:eventid>/update")
@auth.requires_login
@jam_owner_only
def events_update(jamid, eventid):
    # Update an event with the new form data
    title = request.form["title"]
    description = request.form["description"]
    startdate = request.form["startdate"]
    enddate = request.form["enddate"]
    _validate_timestamp(startdate)
    _validate_timestamp(enddate)
    db.query(
            """
            UPDATE jam_events
            SET title = ?, description = ?, startdate = ?, enddate = ?
            WHERE eventid = ? AND jamid = ?
            RETURNING *
            """,
            [title, description, startdate, enddate, eventid, jamid],
            expect_one=True)
    db.commit()
    return redirect(url_for("jams.events_view", jamid=jamid, eventid=eventid))


@bp.get("/<int:jamid>/events/<int:eventid>/delete")
@auth.requires_login
@jam_owner_only
def events_delete(jamid, eventid):
    # Delete an event, redirect to list of all events
    db.query(
            """
            DELETE FROM jam_events
            WHERE eventid = ? AND jamid = ?
            RETURNING *
            """, [eventid, jamid], expect_one=True)
    return redirect(url_for("jams.jam", jamid=jamid))


def _get_jam_by_id(jamid):
    row = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            WHERE jamid = ?
            """, [jamid], expect_one=True)
    return Jam.from_row(row)


def _validate_timestamp(timestamp):
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        abort(400)

@dataclass
class Jam:
    jamid: int
    # TODO: User colors?
    # TODO: User object?
    ownerid: int
    ownername: str
    created: datetime
    title: str
    description: str
    events: list

    @classmethod
    def from_row(cls, row):
        event_rows = db.query(
                """
                SELECT
                    e.eventid,
                    e.jamid,
                    e.title,
                    e.threadid,
                    e.created,
                    e.startdate,
                    e.enddate,
                    e.description,
                    j.title as jam_title,
                    u.username as jam_ownername
                FROM jam_events as e
                INNER JOIN jams as j on e.jamid = j.jamid
                INNER JOIN users as u on j.ownerid = u.userid
                WHERE e.jamid = ?
                """, [row["jamid"]])
        events = [JamEvent.from_row(r) for r in event_rows]
        return cls(
                jamid=row["jamid"],
                title=row["title"],
                description=sanitize_user_text(row["description"] or ""),
                ownerid=row["userid"],
                ownername=row["username"],
                created=datetime.fromisoformat(row["created"]),
                events=events,
        )


@dataclass
class JamEvent:
    eventid: int
    jamid: int
    threadid: int
    created: datetime
    title: str
    startdate: datetime
    enddate: datetime
    description: str
    jam_title: str
    jam_ownername: str
    # TODO: Comment object?
    comments: list

    @classmethod
    def from_row(cls, row):
        comments = db.query("SELECT * FROM comments WHERE threadid = ?", [row["threadid"]])
        return cls(
                eventid=row["eventid"],
                jamid=row["jamid"],
                threadid=row["threadid"],
                created=datetime.fromisoformat(row["created"]),
                title=row["title"],
                startdate=datetime.fromisoformat(row["startdate"]) if row["startdate"] else None,
                enddate=datetime.fromisoformat(row["enddate"]) if row["enddate"] else None,
                description=sanitize_user_text(row["description"] or ""),
                jam_title=row["jam_title"],
                jam_ownername=row["jam_ownername"],
                # TODO: Comment object?
                comments=comments,
        )

