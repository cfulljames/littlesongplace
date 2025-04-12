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

def test_create_jam(client, user):
    response = client.get("/jams/create", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/jams/1"
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

