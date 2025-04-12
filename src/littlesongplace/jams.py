from dataclasses import dataclass
from datetime import datetime, timezone

from flask import Blueprint, g, redirect, render_template, request, url_for

from . import auth, db
from .sanitize import sanitize_user_text

bp = Blueprint("jams", __name__, url_prefix="/jams")

@bp.get("/")
def jams():
    # Show a list of all jams (or events?): current, upcoming, previous
    ...

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
    return redirect(url_for('jams.jam', jamid=jamid))

@bp.get("/<int:jamid>")
def jam(jamid):
    row = db.query(
            """
            SELECT * FROM jams
            INNER JOIN users ON jams.ownerid = users.userid
            WHERE jamid = ?
            """, [jamid], one=True)
    print(type(jamid), row)
    jam = Jam.from_row(row)
    # Show the main jam page
    return render_template("jam.html", jam=jam)

@bp.post("/<int:jamid>/update")
@auth.requires_login
def update(jamid):
    # Update a jam with the new form data, redirect to view page
    title = request.form["title"]
    description = request.form["description"]
    db.query(
            """
            UPDATE jams
            SET title = ?, description = ?
            WHERE jamid = ?
            """, [title, description, jamid])
    db.commit()
    return redirect(url_for('jams.jam', jamid=jamid))

@bp.get("/<int:jamid>/delete")
@auth.requires_login
def delete(jamid):
    # Delete a jam, redirect to the jams list
    ...

@bp.get("/<int:jamid>/events")
def events(jamid):
    # Show a list of all events for the jam (current, upcoming, previous)
    ...

@bp.get("/<int:jamid>/events/create")
@auth.requires_login
def events_create():
    # Create a new event and redirect to the edit form
    ...

@bp.get("/<int:jamid>/events/<int:eventid>")
def events_view(eventid):
    # Show the event page
    ...

@bp.post("/<int:jamid>/events/<int:eventid>/update")
@auth.requires_login
def events_update(jamid):
    # Update an event with the new form data
    ...

@bp.get("/<int:jamid>/events/<int:eventid>/delete")
@auth.requires_login
def events_delete(jamid):
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
        event_rows = db.query("SELECT * FROM jam_events WHERE jamid = ?", [row["jamid"]])
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
                # TODO: Comment object?
                comments=comments,
        )
