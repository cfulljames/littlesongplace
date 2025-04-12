import pytest

from .utils import create_user

@pytest.fixture
def user(client):
    create_user(client, "user", login=True)
    yield "user"

@pytest.fixture
def jam(client):
    client.get("/jams/create")
    return 1

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

# Update event
# Update event invalid event
# Update event not logged in
# Update event other users jam

# Delete event
# Delete event not logged in
# Delete event invalid event
# Delete event other users jam

