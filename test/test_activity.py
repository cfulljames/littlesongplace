from .utils import create_user, create_user_and_song

def test_activity_redirects_when_not_logged_in(client):
    response = client.get("/activity")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_activity_empty_when_user_has_no_notifications(client):
    create_user_and_song(client)
    response = client.get("/activity")
    assert b"Nothing to show" in response.data

def test_activity_for_comment_on_song(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})
    response = client.get("/activity")
    assert b"Nothing to show" in response.data

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

def test_activity_for_comment_on_jam_event(client, user, event):
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool event"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"[Upcoming Event]" in response.data, response.data.decode()
    assert b"hey cool event" in response.data, response.data.decode()

def test_activity_for_reply_to_comment(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    client.post("/comment?threadid=2&replytoid=1", data={"content": "thank you"})

    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/activity")
    assert b"thank you" in response.data

def test_activity_for_reply_to_reply(client):
    create_user_and_song(client)
    create_user(client, "user2")
    create_user(client, "user3", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user2", "password": "password"})
    client.post("/comment?threadid=2&replytoid=1", data={"content": "it really is cool"})

    client.post("/login", data={"username": "user3", "password": "password"})
    client.post("/comment?threadid=2&replytoid=1", data={"content": "thanks for agreeing"})

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
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

    client.get("/delete-song/1")
    response = client.get("/activity")
    assert b"hey cool song" not in response.data

def test_activity_deleted_when_comment_deleted(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/activity")
    assert b"hey cool song" in response.data

    client.get("/delete-comment/1")
    response = client.get("/activity")
    assert b"hey cool song" not in response.data

# New Activity Status ##########################################################

def test_no_new_activity_when_not_logged_in(client):
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

def test_no_new_activity_when_no_activity(client):
    create_user_and_song(client)
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

def test_new_activity_after_comment(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    response = client.get("/new-activity")
    assert response.status_code == 200
    assert response.json["new_activity"]

def test_no_new_activity_after_checking(client):
    create_user_and_song(client)
    create_user(client, "user2", login=True)
    client.post("/comment?threadid=2", data={"content": "hey cool song"})

    client.post("/login", data={"username": "user", "password": "password"})
    client.get("/activity")  # Check activity page

    response = client.get("/new-activity")
    assert response.status_code == 200
    assert not response.json["new_activity"]

