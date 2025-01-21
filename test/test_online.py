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
    response = s.post(url("/signup"), data={"username": "user", "password": "1234asdf!@#$", "password_confirm": "1234asdf!@#$"})
    response = s.post(url("/login"), data={"username": "user", "password": "1234asdf!@#$"})
    response.raise_for_status()
    yield s

def _get_song_list_from_page(page_contents):
    matches = re.findall('data-song="(.*)">', page_contents)
    return [json.loads(html.unescape(m)) for m in matches]

def test_upload_and_delete_song(s):
    response = s.post(
        url("/upload-song"),
        files={"song": open("sample-3s.mp3", "rb")},
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

