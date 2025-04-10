from datetime import datetime, timezone

from flask import Blueprint, g, render_template, url_for

from . import db

bp = Blueprint("jams", __name__, url_prefix="/jams")

@bp.get("/")
def jams():
    # Show a list of all jams (or events?): current, upcoming, previous
    ...

@bp.get("/create")
@requires_login
def create():
    # Create a new jam and redirect to the edit form
    timestamp = datetime.now(timezone.utc).isoformat()
    row = db.query(
            """
            INSERT INTO jams (ownerid, created, title)
            VALUES (?, ?, ?)
            RETURNING jamid
            """,
            args=[g.userid, timestamp, f"New Jam"],
            one=True)
    db.commit()
    jamid = row["jamid"]
    return redirect(url_for('jam', jamid=jamid))

@bp.get("/<jamid>")
def jam(jamid):
    row = db.query("SELECT * FROM jams WHERE jamid = ?", [jamid], one=True)
    # Show the main jam page
    return render_template(
            "jam.html",
            title=row["title"],
            owner=row["userid"],
            description=row["description"])

@bp.post("/<jamid>/update")
@requires_login
def update(jamid):
    # Update a jam with the new form data, redirect to view page
    ...

@bp.get("/<jamid>/delete")
@requires_login
def delete(jamid):
    # Delete a jam, redirect to the jams list
    ...

@bp.get("/<jamid>/events")
def events(jamid):
    # Show a list of all events for the jam (current, upcoming, previous)
    ...

@bp.get("/<jamid>/events/create")
@requires_login
def events_create():
    # Create a new event and redirect to the edit form
    ...

@bp.get("/<jamid>/events/<int:eventid>")
def events_view(eventid):
    # Show the event page
    ...

@bp.post("/<jamid>/events/<int:eventid>/update")
@requires_login
def events_update(jamid):
    # Update an event with the new form data
    ...

@bp.get("/<jamid>/events/<int:eventid>/delete")
@requires_login
def events_delete(jamid):
    # Delete an event, redirect to list of all events
    ...

