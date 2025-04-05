import subprocess
from pathlib import Path
from unittest import mock

import pytest

from .utils import create_user, create_user_and_song, upload_song

TEST_DATA = Path(__file__).parent / "data"

# Upload Song ##################################################################

def test_upload_song_success(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"Successfully uploaded &#39;song title&#39;")

def test_upload_song_bad_title(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"not a valid song title", error=True, title="\r\n")

def test_upload_song_title_too_long(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"cannot be more than 80 characters", error=True, title="a"*81)

def test_upload_song_description_too_long(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"cannot be more than 10k characters", error=True, description="a"*10_001)

def test_upload_song_invalid_tag(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"not a valid tag name", error=True, tags="a\r\na")

def test_upload_song_tag_too_long(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"not a valid tag name", error=True, tags="a"*31)

def test_upload_song_invalid_collab(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"not a valid collaborator name", error=True, collabs="a\r\na")

def test_upload_song_collab_too_long(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"not a valid collaborator name", error=True, collabs="a"*32)

def test_upload_song_invalid_audio(client):
    create_user(client, "user", "password", login=True)
    # Use this script file as the "audio" file
    upload_song(client, b"Invalid audio file", error=True, filename=__file__)

def _create_fake_mp3(*args, **kwargs):
    subprocess_args = args[0]
    if subprocess_args[0] == "ffmpeg":
        # Create "fake" mp3 file by just copying input file
        output_filename = subprocess_args[-1]
        input_filename = subprocess_args[-2]
        with open(input_filename, "rb") as infile, open(output_filename, "wb") as outfile:
            outfile.write(infile.read())

    return subprocess.CompletedProcess([], returncode=0, stdout=b"")

@mock.patch("subprocess.run")
def test_upload_song_from_mp4(fake_run, client):
    fake_run.side_effect = _create_fake_mp3
    create_user(client, "user", "password", login=True)
    upload_song(client, b"Successfully uploaded &#39;song title&#39;", filename=TEST_DATA/"sample-4s.mp4")

@pytest.mark.skip
def test_upload_song_from_youtube(client):
    create_user(client, "user", "password", login=True)
    data = {
        "song-url": "https://youtu.be/5e5Z6gZWiEs",
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }
    response = client.post("/upload-song", data=data)
    assert response.status_code == 302

    response = client.get(f"/users/user")
    assert response.status_code == 200
    assert b"Successfully uploaded &#39;song title&#39;" in response.data

# Edit Song ####################################################################

def test_edit_invalid_song(client):
    create_user(client, "user", "password", login=True)
    response = client.get("/edit-song?songid=1")
    assert response.status_code == 404

def test_edit_invalid_id(client):
    create_user(client, "user", "password", login=True)
    response = client.get("/edit-song?songid=abc")
    assert response.status_code == 404

def test_edit_other_users_song(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"Success")

    create_user(client, "user2", "password", login=True)
    response = client.get("/edit-song?songid=1")
    assert response.status_code == 401

def test_update_song_success(client):
    create_user_and_song(client)
    upload_song(client, b"Successfully updated &#39;song title&#39;", filename=TEST_DATA/"sample-6s.mp3", songid=1)
    response = client.get("/song/1/1")
    assert response.status_code == 200
    with open(TEST_DATA/"sample-6s.mp3", "rb") as expected_file:
        assert response.data == expected_file.read()

@pytest.mark.skip
def test_update_song_from_youtube(client):
    create_user_and_song(client)
    data = {
        "song-url": "https://youtu.be/5e5Z6gZWiEs",
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }
    response = client.post("/upload-song?songid=1", data=data)
    assert response.status_code == 302

    response = client.get(f"/users/user")
    assert response.status_code == 200
    assert b"Successfully updated &#39;song title&#39;" in response.data

def test_update_song_bad_title(client):
    create_user_and_song(client)
    upload_song(client, b"not a valid song title", error=True, songid=1, title="\r\n")

def test_update_song_title_too_long(client):
    create_user_and_song(client)
    upload_song(client, b"cannot be more than 80 characters", error=True, songid=1, title="a"*81)

def test_update_song_description_too_long(client):
    create_user_and_song(client)
    upload_song(client, b"cannot be more than 10k characters", error=True, songid=1, description="a"*10_001)

def test_update_song_invalid_tag(client):
    create_user_and_song(client)
    upload_song(client, b"not a valid tag name", error=True, songid=1, tags="a\r\na")

def test_update_song_tag_too_long(client):
    create_user_and_song(client)
    upload_song(client, b"not a valid tag name", error=True, songid=1, tags="a"*31)

def test_update_song_invalid_collab(client):
    create_user_and_song(client)
    upload_song(client, b"not a valid collaborator name", error=True, songid=1, collabs="a\r\na")

def test_update_song_collab_too_long(client):
    create_user_and_song(client)
    upload_song(client, b"not a valid collaborator name", error=True, songid=1, collabs="a"*32)

def test_update_song_invalid_mp3(client):
    create_user_and_song(client)
    upload_song(client, b"Invalid audio file", error=True, songid=1, filename=__file__)

def test_update_song_invalid_song(client):
    create_user_and_song(client)

    data = {
        "song-file": open(TEST_DATA/"sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=2", data=data)
    assert response.status_code == 400

def test_update_song_invalid_id(client):
    create_user_and_song(client)

    data = {
        "song-file": open(TEST_DATA/"sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=abc", data=data)
    assert response.status_code == 400

def test_update_song_other_users_song(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)

    data = {
        "song-file": open(TEST_DATA/"sample-3s.mp3", "rb"),
        "title": "song title",
        "description": "song description",
        "tags": "tag",
        "collabs": "collab",
    }

    response = client.post(f"/upload-song?songid=1", data=data)
    assert response.status_code == 401

def test_uppercase_tags(client):
    create_user(client, "user", "password", login=True)
    upload_song(client, b"Success", tags="TAG1, tag2")
    response = client.get("/users/user")

    # Both tag versions present
    assert b"TAG1" in response.data
    assert b"tag2" in response.data

    # Edit song
    upload_song(client, b"Success", tags="T1, t2", songid=1)

    # Uppercase tags still work
    response = client.get("/users/user")
    assert b"TAG1" not in response.data
    assert b"T1" in response.data

    assert b"tag2" not in response.data
    assert b"t2" in response.data

# Delete Song ##################################################################

def test_delete_song_success(client):
    create_user_and_song(client)
    response = client.get("/delete-song/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "/users/user"

    response = client.get("/")
    assert b"Deleted &#39;song title&#39;" in response.data

    # mp3 file deleted
    response = client.get("/song/1/1")
    assert response.status_code == 404

def test_delete_song_invalid_song(client):
    create_user_and_song(client)
    response = client.get("/delete-song/2")
    assert response.status_code == 404

def test_delete_song_invalid_id(client):
    create_user_and_song(client)
    response = client.get("/delete-song/abc")
    assert response.status_code == 404

def test_delete_song_other_users_song(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    response = client.get("/delete-song/1")
    assert response.status_code == 401

# Song mp3 file ################################################################

def test_get_song(client):
    create_user_and_song(client)
    response = client.get("/song/1/1")
    with open(TEST_DATA/"sample-3s.mp3", "rb") as mp3file:
        assert response.data == mp3file.read()

def test_get_song_invalid_song(client):
    create_user_and_song(client)
    response = client.get("/song/1/2")
    assert response.status_code == 404

def test_get_song_invalid_user(client):
    create_user_and_song(client)
    response = client.get("/song/2/1")
    assert response.status_code == 404

