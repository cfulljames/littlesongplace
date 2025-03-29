import html
import json
import re

import requests
import pytest

HOST = "http://littlesong.place:8000"

def url(path):
    return HOST + path

@pytest.fixture(scope="module")
def s():
    s = requests.Session()
    # User may already exist, but that's fine - we'll just ignore the signup error
    _login(s, "user", "1234asdf!@#$")
    yield s

def _login(s, username, password):
    s.post(url("/signup"), data={"username": username, "password": password, "password_confirm": password})
    response = s.post(url("/login"), data={"username": username, "password": password})
    response.raise_for_status()

def _get_song_list_from_page(page_contents):
    matches = re.findall('data-song="(.*)">', page_contents)
    return [json.loads(html.unescape(m)) for m in matches]

def test_upload_and_delete_song(s):
    response = s.post(
        url("/upload-song"),
        files={"song-file": open("sample-3s.mp3", "rb")},
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
    response = s.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    assert not any(song["songid"] == songid for song in songs)

def test_comments_and_activity(s):
    # Upload song
    response = s.post(
        url("/upload-song"),
        files={"song-file": open("sample-3s.mp3", "rb")},
        data={"title": "song title", "description": "", "tags": "", "collabs": ""},
    )
    response.raise_for_status()
    songs = _get_song_list_from_page(response.text)
    song = songs[0]
    songid = song["songid"]
    threadid = song["threadid"]

    try:
        _login(s, "user1", "1234asdf!@#$")

        # Comment on song as new user
        response = s.get(
                url(f"/comment?threadid={threadid}"),
                headers={"referer": "/users/user"})
        response.raise_for_status()
        response = s.post(
                url(f"/comment?threadid={threadid}"),
                headers={"referer": f"/comment?threadid={threadid}"},
                data={"content": "hey cool song"})
        response.raise_for_status()
        assert "hey cool song" in response.text

        # Check activity status as original user
        _login(s, "user", "1234asdf!@#$")
        response = s.get(url("/new-activity"))
        assert response.json()["new_activity"] is True

        # Check activity page
        response = s.get(url("/activity"))
        assert "hey cool song" in response.text

    finally:
        # Delete song
        response = s.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
        response.raise_for_status()
        songs = _get_song_list_from_page(response.text)
        assert not any(song["songid"] == songid for song in songs)

@pytest.mark.skip
def test_upload_song_from_youtube(s):
    _login(s, "user", "1234asdf!@#$")

    response = s.post(
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
        response = s.get(url(f"/delete-song/{songid}"), headers={"referer": "/users/user"})
        response.raise_for_status()

