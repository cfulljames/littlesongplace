import functools
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import abort, Blueprint, g, redirect, render_template, request, url_for

from . import auth, db
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


@bp.get("")
def jams():
    # Show a list of all jams: ongoing, upcoming, previous
    rows = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            """)
    jams = [Jam.from_row(r) for r in rows]

    # TODO: Sort into groups based on start/end dates
    return render_template("jams-main.html", ongoing=jams, upcoming=[], past=[])


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
    row = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            WHERE jamid = ?
            """, [jamid], expect_one=True)

    jam = Jam.from_row(row)
    # Show the main jam page
    return render_template("jam.html", jam=jam)


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
    ...


@bp.get("/<int:jamid>/events/<int:eventid>")
def events_view(jamid, eventid):
    # Show the event page
    ...


@bp.post("/<int:jamid>/events/<int:eventid>/update")
@auth.requires_login
@jam_owner_only
def events_update(jamid, eventid):
    # Update an event with the new form data
    ...


@bp.get("/<int:jamid>/events/<int:eventid>/delete")
@auth.requires_login
@jam_owner_only
def events_delete(jamid, eventid):
    # Delete an event, redirect to list of all events
    ...


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
                startdate=datetime.fromisoformat(row["startdate"]),
                enddate=datetime.fromisoformat(row["enddate"]),
                description=sanitize_user_text(row["description"] or ""),
                jam_title=row["jam_title"],
                jam_ownername=row["jam_ownername"],
                # TODO: Comment object?
                comments=comments,
        )

