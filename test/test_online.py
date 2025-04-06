import html
import json
import re
from pathlib import Path

from .utils import url, login

import pytest

TEST_DATA = Path(__file__).parent / "data"

def _get_song_list_from_page(page_contents):
    matches = re.findall('data-song="(.*)">', page_contents)
    return [json.loads(html.unescape(m)) for m in matches]

def test_upload_and_delete_song(session):
    response = session.post(
        url("/upload-song"),
        files={"song-file": open(TEST_DATA/"sample-3s.mp3", "rb")},
        data={
            "title": "song title",
            "description": "song description",
            "tags": "tag1, tag2",
            "collabs": "p1, p2",
        },
    )
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    song = songs[0]

    # Check song uploaded correctly
    assert song["title"] == "song title"
    assert song["description"] == "song description"
    assert song["tags"] == ["tag1", "tag2"]
    assert song["collaborators"] == ["p1", "p2"]

    # Delete song
    songid = song["songid"]
    response = session.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    assert not any(song["songid"] == songid for song in songs)

def test_comments_and_activity(session):
    # Upload song
    response = session.post(
        url("/upload-song"),
        files={"song-file": open(TEST_DATA/"sample-3s.mp3", "rb")},
        data={"title": "song title", "description": "", "tags": "", "collabs": ""},
    )
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    song = songs[0]
    songid = song["songid"]
    threadid = song["threadid"]

    try:
        login(session, "user1", "1234asdf!@#$")

        # Comment on song as new user
        response = session.get(
                url(f"/comment?threadid={threadid}"),
                headers={"referer": "/users/user"})
        response.raise_for_status()
        response = session.post(
                url(f"/comment?threadid={threadid}"),
                headers={"referer": f"/comment?threadid={threadid}"},
                data={"content": "hey cool song"})
        response.raise_for_status()
        assert "hey cool song" in response.text

        # Check activity status as original user
        login(session, "user", "1234asdf!@#$")
        response = session.get(url("/new-activity"))
        assert response.json()["new_activity"] is True

        # Check activity page
        response = session.get(url("/activity"))
        assert "hey cool song" in response.text

    finally:
        # Delete song
        response = session.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
        response.raise_for_status()
        songs = _get_song_list_from_page(response.text)
        assert not any(song["songid"] == songid for song in songs)

@pytest.mark.yt
def test_upload_song_from_youtube(session):
    login(session, "user", "1234asdf!@#$")

    response = session.post(
        url("/upload-song"),
        data={"title": "yt-song", "description": "", "tags": "", "collabs": "", "song-url": "https://youtu.be/5e5Z6gZWiEs"},
    )
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    song = songs[0]
    songid = song["songid"]
    try:
        assert song["title"] == "yt-song"
    finally:
        response = session.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
        response.raise_for_status()

