import pytest

from .utils import create_user

@pytest.fixture
def user(client):
    create_user(client, "user", login=True)
    yield "user"

def test_create_jam(client, user):
    response = client.get("/jams/create", follow_redirects=True)
    assert response.status_code == 200
    assert b"New Jam" in response.data

