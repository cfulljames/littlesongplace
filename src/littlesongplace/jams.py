from flask import Blueprint, render_template

bp = Blueprint("jams", __name__, url_prefix="/jams")

@bp.get("/")
def jams():
    # Show a list of all jams: current, upcoming, previous
    ...

@bp.get("/create")
def create():
    # Create a new jam and redirect to the edit form
    ...

@bp.get("/<jamid>")
def jam(jamid):
    # Show the current/most recent event
    # TODO: Redirect to current event page
    return render_template("jam.html")

@bp.post("/<jamid>/update")
def update(jamid):
    # Update a jam with the new form data, redirect to view page
    ...

@bp.get("/<jamid>/delete")
def delete(jamid):
    # Delete a jam, redirect to the jams list
    ...

@bp.get("/<jamid>/events")
def events(jamid):
    # Show a list of all events for the jam
    ...

@bp.get("/<jamid>/events/create")
def events_create():
    # Create a new event and redirect to the edit form
    ...

@bp.get("/<jamid>/events/<int:eventid>")
def events_view(eventid):
    # Show the event page
    ...

@bp.post("/<jamid>/events/<int:eventid>/update")
def events_update(jamid):
    # Update an event with the new form data
    ...

@bp.get("/<jamid>/events/<int:eventid>/delete")
def events_delete(jamid):
    # Delete an event, redirect to list of all events
    ...

