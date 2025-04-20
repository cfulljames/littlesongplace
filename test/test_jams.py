from datetime import datetime, timedelta, timezone

import pytest

from .utils import create_user, upload_song

# Shared timestamps
today = datetime.now(timezone.utc)
yesterday = (today - timedelta(days=1)).isoformat()
tomorrow = (today + timedelta(days=1)).isoformat()

# Jams #########################################################################

def test_view_invalid_jam(client):
    response = client.get("/jams/1")
    assert response.status_code == 404

def test_create_jam(client, user):
    response = client.get("/jams/create", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/jams/1"
    assert b"New Jam" in response.data

def test_create_jam_not_logged_in(client):
    response = client.get("/jams/create", follow_redirects=True)
    assert response.request.path == "/login"

def test_jams_list(client, user, jam):
    response = client.get("/jams")
    assert response.status_code == 200
    assert b"New Jam" in response.data

def test_update_jam(client, user, jam):
    response = client.post(
            f"/jams/{jam}/update",
            data={"title": "Coolest Jam", "description": "pb and jam"},
            follow_redirects=True)

    assert response.status_code == 200
    assert response.request.path == f"/jams/{jam}"
    assert b"Coolest Jam" in response.data
    assert b"pb and jam" in response.data

def test_update_jam_not_logged_in(client):
    response = client.post("/jams/1/update", follow_redirects=True)
    assert response.request.path == "/login"

def test_update_invalid_jam(client, user):
    response = client.post(
            "/jams/1/update",
            data={"title": "Coolest Jam", "description": "pb and jam"})
    assert response.status_code == 404

def test_update_other_users_jam(client, user, jam):
    create_user(client, "otheruser", login=True)
    response = client.post(
            f"/jams/{jam}/update",
            data={"title": "Coolest Jam", "description": "pb and jam"})
    assert response.status_code == 403

def test_delete_jam(client, user, jam):
    response = client.get(f"/jams/{jam}/delete", follow_redirects=True)
    assert response.request.path == "/jams"
    assert b"New Jam" not in response.data

    response = client.get(f"/jams/{jam}")
    assert response.status_code == 404

def test_delete_jam_not_logged_in(client):
    response = client.get("/jams/1/delete", follow_redirects=True)
    assert response.request.path == "/login"

def test_delete_invalid_jam(client, user):
    response = client.get("/jams/1/delete")
    assert response.status_code == 404

def test_delete_other_users_jam(client, user, jam):
    create_user(client, "otheruser", login=True)
    response = client.get(f"/jams/{jam}/delete")
    assert response.status_code == 403

# Jam Events ###################################################################

def test_view_event_invalid_jamid(client, user):
    response = client.get("/jams/1/events/1")
    assert response.status_code == 404

def test_view_event_invalid_eventid(client, user, jam):
    response = client.get(f"/jams/{jam}/events/1")
    assert response.status_code == 404

def test_create_event(client, user, jam):
    response = client.get(f"/jams/{jam}/events/create", follow_redirects=True)
    assert response.request.path == f"/jams/{jam}/events/1"
    assert b"New Event" in response.data

def test_create_event_not_logged_in(client, user, jam):
    response = client.get("/logout")
    response = client.get(f"/jams/{jam}/events/create", follow_redirects=True)
    assert response.request.path == "/login"

def test_create_event_on_other_users_jam(client, user, jam):
    create_user(client, "otheruser", login=True)
    response = client.get(f"/jams/{jam}/events/create", follow_redirects=True)
    assert response.status_code == 403

def _to_utc(timestamp):
    return (datetime
            .fromisoformat(timestamp)
            .astimezone(timezone.utc)
            .isoformat())

def _get_event_data(**kwargs):
    event_data = {
            "title": "Event Title",
            "description": "description of the event",
            "startdate": _to_utc("2040-01-01T00:00:00"),
            "enddate": _to_utc("2040-01-02T00:00:00"),
    }
    for k, v in kwargs.items():
        event_data[k] = v
    return event_data

def test_update_event(client, user, jam, event):
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(), follow_redirects=True)
    assert response.request.path == f"/jams/{jam}/events/{event}"
    assert b"Event Title" in response.data
    assert b"description of the event" in response.data
    assert b"2040-01-01" in response.data
    assert b"2040-01-02" in response.data

def test_update_event_invalid_eventid(client, user, jam):
    response = client.post(f"/jams/{jam}/events/1/update", data=_get_event_data())
    assert response.status_code == 404

def test_update_event_invalid_jamid(client, user, event):
    response = client.post(f"/jams/2/events/{event}/update", data=_get_event_data())
    assert response.status_code == 404

def test_update_event_not_logged_in(client, user, jam, event):
    response = client.get("/logout")
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(),
            follow_redirects=True)
    assert response.request.path == "/login"

def test_update_event_other_users_jam(client, user, jam, event):
    create_user(client, "otheruser", login=True)
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(),
            follow_redirects=True)
    assert response.status_code == 403

def test_update_event_invalid_startdate(client, user, jam, event):
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(startdate="notadate"),
            follow_redirects=True)
    assert response.status_code == 400

def test_update_event_invalid_enddate(client, user, jam, event):
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(enddate="notadate"),
            follow_redirects=True)
    assert response.status_code == 400

def test_delete_event(client, user, jam, event):
    response = client.get(f"/jams/{jam}/events/{event}/delete", follow_redirects=True)
    assert response.request.path == f"/jams/{jam}"
    assert b"Event Title" not in response.data

def test_delete_event_not_logged_in(client, user, jam, event):
    client.get("/logout")
    response = client.get(f"/jams/{jam}/events/{event}/delete", follow_redirects=True)
    assert response.request.path == "/login"

def test_delete_event_invalid_jamid(client, user, jam, event):
    response = client.get(f"/jams/2/events/{event}/delete", follow_redirects=True)
    assert response.status_code == 404

def test_delete_event_invalid_eventid(client, user, jam, event):
    response = client.get(f"/jams/{jam}/events/2/delete", follow_redirects=True)
    assert response.status_code == 404

def test_delete_event_other_users_jam(client, user, jam, event):
    create_user(client, "otheruser", login=True)
    response = client.get(f"/jams/{jam}/events/{event}/delete", follow_redirects=True)
    assert response.status_code == 403

def _create_event(client, jam, title, startdate, enddate):
    response = client.get(f"/jams/{jam}/events/create", follow_redirects=True)
    eventid = int(response.request.path[-1])
    client.post(
            f"/jams/{jam}/events/{eventid}/update",
            data=_get_event_data(title=title, startdate=startdate, enddate=enddate))

def _assert_appear_in_order(page, values):
    last_index = 0
    for v in values:
        assert v in page
        index = page.index(v, last_index+1)
        assert index > last_index
        last_index = index

def _create_past_present_future_events(client, jam):
    _create_event(client, jam, "PastJam", yesterday, yesterday)
    _create_event(client, jam, "OngoingJam", yesterday, tomorrow)
    _create_event(client, jam, "UpcomingJam", tomorrow, tomorrow)

    response = client.get("/jams/create", follow_redirects=True)
    otherjam = int(response.request.path[-1])
    _create_event(client, otherjam, "OtherJam", tomorrow, tomorrow)

def test_jam_events_sorted_on_jams_page(client, user, jam):
    _create_past_present_future_events(client, jam)

    response = client.get("/jams")
    _assert_appear_in_order(
            response.data,
            [
                b"Ongoing Events",
                b"OngoingJam",

                b"Upcoming Events",
                b"[Upcoming Event]", # Upcoming jam name hidden
                b"[Upcoming Event]", # Upcoming jam name hidden

                b"Recent Events",
                b"PastJam",

                b"All Jams",
                b"New Jam",
                b"New Jam",
            ])

def test_jam_events_sorted_on_jam_info_page(client, user, jam):
    _create_past_present_future_events(client, jam)

    response = client.get(f"/jams/{jam}")
    assert b"OtherJam" not in response.data  # Only events for this jam

    _assert_appear_in_order(
            response.data,
            [
                b"Ongoing Events",
                b"OngoingJam",

                b"Upcoming Events",
                b"[Upcoming Event]", # Upcoming jam name hidden

                b"Past Events",
                b"PastJam",
            ])

# Song Submissions #############################################################

def test_submit_song_to_event(client, user, jam, event):
    client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(startdate=yesterday, enddate=tomorrow))
    # Song always visible to owner
    upload_song(client, b"Success", eventid=event)
    response = client.get(f"/jams/{jam}/events/{event}")
    assert b"song title" in response.data, response.data.decode()

    # Check for event title on song page
    response = client.get(f"/song/1/1?action=view")
    assert b"Event Title" in response.data, response.data.decode()

def test_submitted_song_hidden_before_enddate(client, user, jam, event):
    client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(startdate=yesterday, enddate=tomorrow))
    upload_song(client, b"Success", eventid=event)
    client.get("/logout")  # Log out to test public visibility

    response = client.get(f"/jams/{jam}/events/{event}")
    assert b"song title" not in response.data, response.data.decode()

def test_submitted_song_visible_after_enddate(client, user, jam, event):
    response = client.post(
            f"/jams/{jam}/events/{event}/update",
            data=_get_event_data(startdate=yesterday, enddate=yesterday),
            follow_redirects=True)
    upload_song(client, b"Success", eventid=event)
    client.get("/logout")  # Log out to test public visibility

    response = client.get(f"/jams/{jam}/events/{event}")
    assert b"song title" in response.data, response.data.decode()

