import html
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pytest
from flask import session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main

@pytest.fixture
def app():
    # Use temporary data directory
    with tempfile.TemporaryDirectory() as data_dir:
        main.DATA_DIR = Path(data_dir)

        # Initialize Database
        with main.app.app_context():
            db = sqlite3.connect(main.DATA_DIR / "database.db")
            with main.app.open_resource('schema.sql', mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()
            db.close()

        yield main.app

@pytest.fixture
def client(app):
    # Mock bcrypt to speed up tests
    with patch.object(bcrypt, "hashpw", lambda passwd, salt: passwd), \
        patch.object(bcrypt, "checkpw", lambda passwd, saved: passwd == saved):
        yield app.test_client()

################################################################################
# Signup
################################################################################

def test_signup_get(client):
    response = client.get("/signup")
    assert b"Create a new account" in response.data

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

def _create_user(client, username, password="password", login=False):
    response = _post_signup_form(client, username, password)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    if login:
        response = client.post("/login", data={"username": username, "password": password})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/users/{username}"

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
# Profile/Bio
################################################################################

def test_default_bio_empty(client):
    _create_user(client, "user", "password")

    response = client.get("/users/user")
    assert b'<div class="profile-bio" id="profile-bio"></div>' in response.data

def test_update_bio(client):
    _create_user(client, "user", "password", login=True)

    response = client.post("/edit-profile", data={"bio": "this is the bio", "pfp": (b"", "", "aplication/octet-stream")})
    assert response.status_code == 302
    assert response.headers["Location"] == "/users/user"

    response = client.get("/users/user")
    assert b'<div class="profile-bio" id="profile-bio">this is the bio</div>' in response.data

def test_upload_pfp(client):
    _create_user(client, "user", "password", login=True)
    response = client.post("/edit-profile", data={"bio": "", "pfp": open("lsp_notes.png", "rb")})
    assert response.status_code == 302

def test_edit_profile_not_logged_in(client):
    response = client.post("/edit-profile", data={"bio": "", "pfp": open("lsp_notes.png", "rb")})
    assert response.status_code == 401

def test_get_pfp(client):
    _create_user(client, "user", "password", login=True)
    client.post("/edit-profile", data={"bio": "", "pfp": open("lsp_notes.png", "rb")})

    response = client.get("/pfp/1")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    # Can't check image file, since site has modified it

def test_get_pfp_no_file(client):
    _create_user(client, "user", "password", login=True)
    # User exists but doesn't have a pfp
    response = client.get("/pfp/1")
    assert response.status_code == 404

def test_get_pfp_invalid_user(client):
    response = client.get("/pfp/1")
    # User doesn't exist
    assert response.status_code == 404

################################################################################
# Upload Song
################################################################################

def _test_upload_song(client, msg, error=False, songid=None, user="user", filename="sample-3s.mp3", **kwargs):
    song_file = open(filename, "rb")

    data = {
        "song": song_file,
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }
    for k, v in kwargs.items():
        data[k] = v

    if songid:
        response = client.post(f"/upload-song?songid={songid}", data=data)
    else:
        response = client.post("/upload-song", data=data)

    assert response.status_code == 302
    if error:
        assert response.headers["Location"] == "None"
    else:
        assert response.headers["Location"] == f"/users/{user}"

    response = client.get(f"/users/{user}")
    assert msg in response.data

def test_upload_song_success(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"Successfully uploaded &#39;song title&#39;")

def test_upload_song_bad_title(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"not a valid song title", error=True, title="\r\n")

def test_upload_song_title_too_long(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"cannot be more than 80 characters", error=True, title="a"*81)

def test_upload_song_description_too_long(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"cannot be more than 10k characters", error=True, description="a"*10_001)

def test_upload_song_invalid_tag(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"not a valid tag name", error=True, tags="a\r\na")

def test_upload_song_tag_too_long(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"not a valid tag name", error=True, tags="a"*31)

def test_upload_song_invalid_collab(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"not a valid collaborator name", error=True, collabs="a\r\na")

def test_upload_song_collab_too_long(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"not a valid collaborator name", error=True, collabs="a"*32)

def test_upload_song_invalid_audio(client):
    _create_user(client, "user", "password", login=True)
    # Use this script file as the "audio" file
    _test_upload_song(client, b"Invalid audio file", error=True, filename=__file__)

def test_upload_song_from_mp4(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"Successfully uploaded &#39;song title&#39;", filename="sample-4s.mp4")

################################################################################
# Edit Song
################################################################################

def test_edit_invalid_song(client):
    _create_user(client, "user", "password", login=True)
    response = client.get("/edit-song?songid=1")
    assert response.status_code == 404

def test_edit_invalid_id(client):
    _create_user(client, "user", "password", login=True)
    response = client.get("/edit-song?songid=abc")
    assert response.status_code == 404

def test_edit_other_users_song(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"Success")

    _create_user(client, "user2", "password", login=True)
    response = client.get("/edit-song?songid=1")
    assert response.status_code == 401

def _create_user_and_song(client, username="user"):
    _create_user(client, username, "password", login=True)
    _test_upload_song(client, b"Success", user=username)

def test_update_song_success(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"Successfully updated &#39;song title&#39;", filename="sample-6s.mp3", songid=1)
    response = client.get("/song/1/1")
    assert response.status_code == 200
    with open("sample-6s.mp3", "rb") as expected_file:
        assert response.data == expected_file.read()

def test_update_song_bad_title(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"not a valid song title", error=True, songid=1, title="\r\n")

def test_update_song_title_too_long(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"cannot be more than 80 characters", error=True, songid=1, title="a"*81)

def test_update_song_description_too_long(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"cannot be more than 10k characters", error=True, songid=1, description="a"*10_001)

def test_update_song_invalid_tag(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"not a valid tag name", error=True, songid=1, tags="a\r\na")

def test_update_song_tag_too_long(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"not a valid tag name", error=True, songid=1, tags="a"*31)

def test_update_song_invalid_collab(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"not a valid collaborator name", error=True, songid=1, collabs="a\r\na")

def test_update_song_collab_too_long(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"not a valid collaborator name", error=True, songid=1, collabs="a"*32)

def test_update_song_invalid_mp3(client):
    _create_user_and_song(client)
    song_file = open(__file__, "rb")
    _test_upload_song(client, b"Invalid audio file", error=True, songid=1, song=song_file)

def test_update_song_invalid_song(client):
    _create_user_and_song(client)

    data = {
        "song": open("sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=2", data=data)
    assert response.status_code == 400

def test_update_song_invalid_id(client):
    _create_user_and_song(client)

    data = {
        "song": open("sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=abc", data=data)
    assert response.status_code == 400

def test_update_song_other_users_song(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)

    data = {
        "song": open("sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=1", data=data)
    assert response.status_code == 401

def test_uppercase_tags(client):
    _create_user(client, "user", "password", login=True)
    _test_upload_song(client, b"Success", tags="TAG1, tag2")
    response = client.get("/users/user")

    # Both tag versions present
    assert b"TAG1" in response.data
    assert b"tag2" in response.data

    # Edit song
    _test_upload_song(client, b"Success", tags="T1, t2", songid=1)

    # Uppercase tags still work
    response = client.get("/users/user")
    assert b"TAG1" not in response.data
    assert b"T1" in response.data

    assert b"tag2" not in response.data
    assert b"t2" in response.data

################################################################################
# Delete Song
################################################################################

def test_delete_song_success(client):
    _create_user_and_song(client)
    response = client.get("/delete-song/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "None"

    response = client.get("/")
    assert b"Deleted &#39;song title&#39;" in response.data

    # mp3 file deleted
    response = client.get("/song/1/1")
    assert response.status_code == 404

def test_delete_song_invalid_song(client):
    _create_user_and_song(client)
    response = client.get("/delete-song/2")
    assert response.status_code == 404

def test_delete_song_invalid_id(client):
    _create_user_and_song(client)
    response = client.get("/delete-song/abc")
    assert response.status_code == 404

def test_delete_song_other_users_song(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    response = client.get("/delete-song/1")
    assert response.status_code == 401

################################################################################
# Song mp3 file
################################################################################

def test_get_song(client):
    _create_user_and_song(client)
    response = client.get("/song/1/1")
    with open("sample-3s.mp3", "rb") as mp3file:
        assert response.data == mp3file.read()

def test_get_song_invalid_song(client):
    _create_user_and_song(client)
    response = client.get("/song/1/2")
    assert response.status_code == 404

def test_get_song_invalid_user(client):
    _create_user_and_song(client)
    response = client.get("/song/2/1")
    assert response.status_code == 404

################################################################################
# Song Lists (Profile/Homepage/Songs)
################################################################################

# Profile

def _get_song_list_from_page(client, url):
    response = client.get(url)
    matches = re.findall('data-song="(.*)">', response.data.decode())
    return [json.loads(html.unescape(m)) for m in matches]

def test_profile_songs_one_song(client):
    _create_user_and_song(client)
    songs = _get_song_list_from_page(client, "/users/user")

    assert len(songs) == 1
    assert songs[0]["title"] == "song title"

def test_profile_songs_two_songs(client):
    _create_user_and_song(client)
    _test_upload_song(client, b"Success", title="title2")
    songs = _get_song_list_from_page(client, "/users/user")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "title2"
    assert songs[1]["title"] == "song title"

# Homepage

def test_homepage_songs_two_songs(client):
    _create_user(client, "user1", "password", login=True)
    _test_upload_song(client, b"Success", user="user1", title="song1")

    _create_user(client, "user2", "password", login=True)
    _test_upload_song(client, b"Success", user="user2", title="song2")

    songs = _get_song_list_from_page(client, "/")

    # Newest first (all songs)
    assert len(songs) == 2
    assert songs[0]["title"] == "song2"
    assert songs[0]["username"] == "user2"

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

# Songs by tag

def test_songs_by_tag_no_user(client):
    _create_user(client, "user1", "password", login=True)
    _test_upload_song(client, b"Success", user="user1", title="song1", tags="tag")

    _create_user(client, "user2", "password", login=True)
    _test_upload_song(client, b"Success", user="user2", title="song2", tags="")
    _test_upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?tag=tag")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "song3"
    assert songs[0]["username"] == "user2"

    # Song 2 not shown, no tag

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

def test_songs_by_tag_with_user(client):
    _create_user(client, "user1", "password", login=True)
    _test_upload_song(client, b"Success", user="user1", title="song1", tags="tag")
    _test_upload_song(client, b"Success", user="user1", title="song2", tags="")

    _create_user(client, "user2", "password", login=True)
    _test_upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?tag=tag&user=user1")

    assert len(songs) == 1
    assert songs[0]["title"] == "song1"
    assert songs[0]["username"] == "user1"
    # Song 2 not shown, no tag; song 3 not shown, by different user

def test_songs_by_user(client):
    _create_user(client, "user1", "password", login=True)
    _test_upload_song(client, b"Success", user="user1", title="song1", tags="tag")
    _test_upload_song(client, b"Success", user="user1", title="song2", tags="")

    _create_user(client, "user2", "password", login=True)
    _test_upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?user=user1")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "song2"
    assert songs[0]["username"] == "user1"

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

    # Song 3 not shown, by different user

def test_single_song(client):
    _create_user(client, "user1", "password", login=True)
    _test_upload_song(client, b"Success", user="user1", title="song1", tags="tag")

    songs = _get_song_list_from_page(client, "/song/1/1?action=view")

    assert len(songs) == 1
    assert songs[0]["title"] == "song1"
    assert songs[0]["username"] == "user1"

################################################################################
# Site News
################################################################################

def test_site_news(client):
    response = client.get("/site-news")
    assert response.status_code == 200
    assert b"Site News" in response.data

################################################################################
# Comments - Normal Flow
################################################################################

def _create_user_song_and_comment(client, content):
    _create_user_and_song(client)
    response = client.post("/comment?songid=1", data={"content": content})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

def test_comment_page_no_reply_or_edit(client):
    _create_user_and_song(client)
    response = client.get("/comment?songid=1")
    assert response.status_code == 200
    assert not b"reply" in response.data

def test_post_comment(client):
    _create_user_and_song(client)
    response = client.post("/comment?songid=1", data={"content": "comment text here"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"comment text here" in response.data

def test_edit_comment(client):
    _create_user_song_and_comment(client, "comment text here")

    response = client.post("/comment?songid=1&commentid=1", data={"content": "new comment content"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"new comment content" in response.data

def test_delete_comment(client):
    _create_user_song_and_comment(client, "comment text here")

    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "None"

    response = client.get("/song/1/1?action=view")
    assert b"comment text here" not in response.data

def test_delete_song_with_comments(client):
    _create_user_song_and_comment(client, "comment text here")
    response = client.get("/delete-song/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "None" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert response.status_code == 404  # Song deleted

def test_reply_to_comment(client):
    _create_user_song_and_comment(client, "parent comment")

    response = client.post("/comment?songid=1&replytoid=1", data={"content": "child comment"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"parent comment" in response.data
    assert b"child comment" in response.data

################################################################################
# Comments - Auth Status and Errors
################################################################################

def test_comment_page_redirects_when_not_logged_in(client):
    _create_user_and_song(client)
    client.get("/logout")

    response = client.get("/comment?songid=1")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_post_comment_redirects_when_not_logged_in(client):
    _create_user_and_song(client)
    client.get("/logout")

    response = client.post("/comment?songid=1", data={"content": "should fail"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_add_comment_link_not_shown_when_not_logged_in(client):
    _create_user_and_song(client)
    response = client.get("/song/1/1?action=view")
    assert b"Add a Comment" in response.data

    client.get("/logout")
    response = client.get("/song/1/1?action=view")
    assert b"Add a Comment" not in response.data

def test_delete_comment_not_logged_in(client):
    _create_user_song_and_comment(client, "comment text here")
    client.get("/logout")

    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    # Comment not deleted
    response = client.get("/song/1/1?action=view")
    assert b"comment text here" in response.data

def test_song_owner_can_delete_other_users_comment(client):
    _create_user(client, "user1")
    _create_user_and_song(client, "user2")

    # user1 comments on user2's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?songid=1", data={"content": "mean comment"})
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

    # user2 deletes user1's rude comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" not in response.data

def test_rando_cannot_delete_other_users_comment(client):
    _create_user(client, "user1")
    _create_user(client, "user2")
    _create_user_and_song(client, "user3")

    # user1 comments on user3's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?songid=1", data={"content": "nice comment"})
    response = client.get("/song/3/1?action=view")
    assert b"nice comment" in response.data

    # user2 cannot delete user1's comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/delete-comment/1")
    assert response.status_code == 403
    response = client.get("/song/3/1?action=view")
    assert b"nice comment" in response.data

def test_cannot_edit_other_users_comment(client):
    _create_user(client, "user1")
    _create_user_and_song(client, "user2")

    # user1 comments on user2's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?songid=1", data={"content": "mean comment"})
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

    # user2 cannot edit user1's rude comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.post("/comment?songid=1&commentid=1", data={"content": "im a meanie"})
    assert response.status_code == 403
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

def test_comment_invalid_songid(client):
    _create_user_and_song(client)
    response = client.post("/comment?songid=2", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?songid=2")
    assert response.status_code == 404

def test_comment_invalid_replytoid(client):
    _create_user_and_song(client)
    response = client.post("/comment?songid=1&replytoid=1", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?songid=1&replytoid=1")
    assert response.status_code == 404

def test_comment_invalid_commentid(client):
    _create_user_and_song(client)
    response = client.post("/comment?songid=1&commentid=1", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?songid=1&commentid=1")
    assert response.status_code == 404

def test_comment_no_songid(client):
    _create_user_and_song(client)
    response = client.post("/comment", data={"content": "broken comment"})
    assert response.status_code == 400

    response = client.get("/comment")
    assert response.status_code == 400

def test_delete_invalid_comment_id(client):
    _create_user_and_song(client)
    response = client.get("/delete-comment/1")
    assert response.status_code == 404

################################################################################
# Activity
################################################################################

def test_activity_redirects_when_not_logged_in(client):
    response = client.get("/activity")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_activity_empty_when_user_has_no_notifications(client):
    _create_user_and_song(client)
    response = client.get("/activity")
    assert b"Nothing to show" in response.data

def test_activity_for_comment_on_song(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})
    response = client.get("/activity")
    assert b"Nothing to show" in response.data

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

def test_activity_for_reply_to_comment(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    client.post("/comment?songid=1&replytoid=1", data={"content": "thank you"})

    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/activity")
    assert b"thank you" in response.data

def test_activity_for_reply_to_reply(client):
    _create_user_and_song(client)
    _create_user(client, "user2")
    _create_user(client, "user3", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user2", "password": "password"})
    client.post("/comment?songid=1&replytoid=1", data={"content": "it really is cool"})

    client.post("/login", data={"username": "user3", "password": "password"})
    client.post("/comment?songid=1&replytoid=1", data={"content": "thanks for agreeing"})

    # Song owner gets all three notifications
    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data
    assert b"it really is cool" in response.data
    assert b"thanks for agreeing" in response.data

    # user2 gets reply notification
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/activity")
    assert b"thanks for agreeing" in response.data

    # user3 gets reply notification
    client.post("/login", data={"username": "user3", "password": "password"})
    response = client.get("/activity")
    assert b"it really is cool" in response.data

def test_activity_deleted_when_song_deleted(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

    client.get("/delete-song/1")
    response = client.get("/activity")
    assert b"hey cool song" not in response.data

def test_activity_deleted_when_comment_deleted(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

    client.get("/delete-comment/1")
    response = client.get("/activity")
    assert b"hey cool song" not in response.data

################################################################################
# New Activity Status
################################################################################

def test_no_new_activity_when_not_logged_in(client):
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

def test_no_new_activity_when_no_activity(client):
    _create_user_and_song(client)
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

def test_new_activity_after_comment(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert response.json["new_activity"]

def test_no_new_activity_after_checking(client):
    _create_user_and_song(client)
    _create_user(client, "user2", login=True)
    client.post("/comment?songid=1", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    client.get("/activity")  # Check activity page

    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

