from pathlib import Path

HOST = "http://littlesong.place:8000"
TEST_DATA = Path(__file__).parent / "data"

def url(path):
    return HOST + path

def login(session, username, password):
    session.post(url("/signup"), data={"username": username, "password": password, "password_confirm": password})
    response = session.post(url("/login"), data={"username": username, "password": password})
    response.raise_for_status()

def post_signup_form(client, username, password, password_confirm=None):
    if password_confirm is None:
        password_confirm = password
    return client.post(
            "/signup",
            data=dict(username=username, password=password, password_confirm=password_confirm))

def create_user(client, username, password="password", login=False):
    response = post_signup_form(client, username, password)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    if login:
        response = client.post("/login", data={"username": username, "password": password})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/users/{username}"

def create_user_and_song(client, username="user"):
    create_user(client, username, "password", login=True)
    upload_song(client, b"Success", user=username)

def upload_song(client, msg, error=False, songid=None, user="user", userid=1, filename=TEST_DATA/"sample-3s.mp3", **kwargs):
    song_file = open(filename, "rb")

    data = {
        "song-file": song_file,
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
    elif songid:
        assert response.headers["Location"] == f"/song/{userid}/{songid}?action=view"
    else:
        assert response.headers["Location"] == f"/users/{user}"

    response = client.get(f"/users/{user}")
    assert msg in response.data

