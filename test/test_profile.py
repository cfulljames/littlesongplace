from pathlib import Path
from .utils import create_user

TEST_DATA = Path(__file__).parent / "data"

def test_default_bio_empty(client):
    create_user(client, "user", "password")

    response = client.get("/users/user")
    assert b'<div class="profile-bio" id="profile-bio"></div>' in response.data

def test_update_bio(client):
    create_user(client, "user", "password", login=True)

    response = client.post("/edit-profile", data={
        "bio": "this is the bio",
        "pfp": (b"", "", "aplication/octet-stream"),
        "fgcolor": "#000000",
        "bgcolor": "#FFFF00",
        "accolor": "#FF00FF",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/users/user"

    # Check bio updated
    response = client.get("/users/user")
    assert b'<div class="profile-bio" id="profile-bio">this is the bio</div>' in response.data

    # Check user colors applied
    assert b'bgcolor="#FFFF00"' in response.data
    assert b'fgcolor="#000000"' in response.data
    assert b'accolor="#FF00FF"' in response.data

def test_upload_pfp(client):
    create_user(client, "user", "password", login=True)
    response = client.post("/edit-profile", data={
        "bio": "",
        "pfp": open(TEST_DATA/"lsp_notes.png", "rb"),
        "fgcolor": "#000000",
        "bgcolor": "#000000",
        "accolor": "#000000",
    })
    assert response.status_code == 302

def test_edit_profile_not_logged_in(client):
    response = client.post("/edit-profile", data={
        "bio": "",
        "pfp": open(TEST_DATA/"lsp_notes.png", "rb"),
        "fgcolor": "#000000",
        "bgcolor": "#000000",
        "accolor": "#000000",
    })
    assert response.status_code == 401

def test_get_pfp(client):
    create_user(client, "user", "password", login=True)
    client.post("/edit-profile", data={
        "bio": "",
        "pfp": open(TEST_DATA/"lsp_notes.png", "rb"),
        "fgcolor": "#000000",
        "bgcolor": "#000000",
        "accolor": "#000000",
    })

    response = client.get("/pfp/1")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    # Can't check image file, since site has modified it

def test_get_pfp_no_file(client):
    create_user(client, "user", "password", login=True)
    # User exists but doesn't have a pfp
    response = client.get("/pfp/1")
    assert response.status_code == 404

def test_get_pfp_invalid_user(client):
    response = client.get("/pfp/1")
    # User doesn't exist
    assert response.status_code == 404
