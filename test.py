import tempfile
from pathlib import Path

import pytest
from flask import session

import main

@pytest.fixture
def app():
    # Use temporary data directory
    with tempfile.TemporaryDirectory() as data_dir:
        main.DATA_DIR = Path(data_dir)

        # Initialize Database
        with main.app.app_context():
            db = main.get_db()
            with main.app.open_resource('schema.sql', mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()

        yield main.app

@pytest.fixture
def client(app):
    return app.test_client()

################################################################################
# Signup
################################################################################

def test_signup_get(client):
    response = client.get("/signup")
    assert b"Rules" in response.data

def _post_signup_form(client, username, password, password_confirm=None):
    if password_confirm is None:
        password_confirm = password
    return client.post(
            "/signup",
            data=dict(username=username, password=password, password_confirm=password_confirm))

def test_signup_success(client):
    response = _post_signup_form(client, "user", "password")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    response = client.get("/login")
    assert b"User created" in response.data

def _test_signup_error(client, username, password, password_confirm, msg):
    response = _post_signup_form(client, username, password, password_confirm)
    assert response.status_code == 302
    assert response.headers["Location"] == "None"

    response = client.get("/signup")
    assert b"User created" not in response.data
    assert msg in response.data

def test_signup_username_invalid_characters(client):
    _test_signup_error(client, "user@gmail.com", "password", "password", b"special characters")

def test_signup_username_too_short(client):
    _test_signup_error(client, "us", "password", "password", b"at least 3 characters")

def test_signup_username_too_long(client):
    _test_signup_error(client, "a"*31, "password", "password", b"more than 30 characters")

def test_signup_passwords_dont_match(client):
    _test_signup_error(client, "user", "password", "passwor", b"Passwords do not match")

def test_signup_password_too_short(client):
    _test_signup_error(client, "user", "passwor", "passwor", b"at least 8 characters")

def test_signup_user_exists(client):
    # Success the first time
    response = _post_signup_form(client, "user", "password")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    response = client.get("/login")
    assert b"User created" in response.data

    # Error the second time
    _test_signup_error(client, "user", "password", "password", b"already taken")

################################################################################
# Login/Logout
################################################################################

def test_login_get(client):
    response = client.get("/login")
    assert b"Sign In" in response.data

def _create_user(client, username, password):
    response = _post_signup_form(client, username, password)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_login_success(client):
    _create_user(client, "username", "password")
    response = client.post("/login", data={"username": "username", "password": "password"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/users/username"

    response = client.get("/users/username")
    assert b"Signed in as username" in response.data

def test_login_invalid_username(client):
    _create_user(client, "username", "password")
    response = client.post("/login", data={"username": "incorrect", "password": "password"})
    assert response.status_code == 200
    assert b"Invalid username/password" in response.data

def test_login_invalid_username(client):
    _create_user(client, "username", "password")
    response = client.post("/login", data={"username": "username", "password": "incorrect"})
    assert response.status_code == 200
    assert b"Invalid username/password" in response.data

def test_logout(client, app):
    with client:
        _create_user(client, "username", "password")
        response = client.post("/login", data={"username": "username", "password": "password"})
        assert response.status_code == 302

        assert session["username"] == "username"
        assert session["userid"] == 1

        response = client.get("/logout")
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

        assert "username" not in session
        assert "userid" not in session

################################################################################
# Profile
################################################################################

# TODO

################################################################################
# Upload/Edit Song
################################################################################

# TODO

################################################################################
# Song Lists
################################################################################

# TODO

