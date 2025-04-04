from .utils import create_user, create_user_and_song, create_user_song_and_comment, create_user_song_and_playlist

# Comments - Normal Flow #######################################################

def test_comment_page_no_reply_or_edit(client):
    create_user_and_song(client)
    response = client.get("/comment?threadid=2")
    assert response.status_code == 200
    assert not b"reply" in response.data

def test_post_comment(client):
    create_user_and_song(client)
    response = client.post("/comment?threadid=2", data={"content": "comment text here"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"comment text here" in response.data

def test_edit_comment(client):
    create_user_song_and_comment(client, "comment text here")

    response = client.post("/comment?threadid=2&commentid=1", data={"content": "new comment content"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"new comment content" in response.data

def test_delete_comment(client):
    create_user_song_and_comment(client, "comment text here")

    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "None"

    response = client.get("/song/1/1?action=view")
    assert b"comment text here" not in response.data

def test_delete_song_with_comments(client):
    create_user_song_and_comment(client, "comment text here")
    response = client.get("/delete-song/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "/users/user"

    response = client.get("/song/1/1?action=view")
    assert response.status_code == 404  # Song deleted

def test_reply_to_comment(client):
    create_user_song_and_comment(client, "parent comment")

    response = client.post("/comment?threadid=2&replytoid=1", data={"content": "child comment"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

    response = client.get("/song/1/1?action=view")
    assert b"parent comment" in response.data
    assert b"child comment" in response.data

def test_comment_on_profile(client):
    create_user(client, "user1", login=True)
    response = client.get("/comment?threadid=1", headers={"Referer": "/users/user1"})
    response = client.post("/comment?threadid=1", data={"content": "comment on profile"}, follow_redirects=True)
    assert response.request.path == "/users/user1"
    assert b"comment on profile" in response.data

def test_comment_on_playlist(client):
    create_user_song_and_playlist(client)
    response = client.get("/comment?threadid=3", headers={"Referer": "/playlists/1"})
    response = client.post("/comment?threadid=3", data={"content": "comment on playlist"}, follow_redirects=True)
    assert response.request.path == "/playlists/1"
    assert b"comment on playlist" in response.data

# Comments - Auth Status and Errors ############################################

def test_comment_page_redirects_when_not_logged_in(client):
    create_user_and_song(client)
    client.get("/logout")

    response = client.get("/comment?threadid=2")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_post_comment_redirects_when_not_logged_in(client):
    create_user_and_song(client)
    client.get("/logout")

    response = client.post("/comment?threadid=2", data={"content": "should fail"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

def test_add_comment_link_not_shown_when_not_logged_in(client):
    create_user_and_song(client)
    response = client.get("/song/1/1?action=view")
    assert b"Add a Comment" in response.data

    client.get("/logout")
    response = client.get("/song/1/1?action=view")
    assert b"Add a Comment" not in response.data

def test_delete_comment_not_logged_in(client):
    create_user_song_and_comment(client, "comment text here")
    client.get("/logout")

    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    # Comment not deleted
    response = client.get("/song/1/1?action=view")
    assert b"comment text here" in response.data

def test_song_owner_can_delete_other_users_comment(client):
    create_user(client, "user1")
    create_user_and_song(client, "user2")

    # user1 comments on user2's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?threadid=3", data={"content": "mean comment"})
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

    # user2 deletes user1's rude comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/delete-comment/1")
    assert response.status_code == 302
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" not in response.data

def test_rando_cannot_delete_other_users_comment(client):
    create_user(client, "user1")
    create_user(client, "user2")
    create_user_and_song(client, "user3")

    # user1 comments on user3's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?threadid=4", data={"content": "nice comment"})
    response = client.get("/song/3/1?action=view")
    assert b"nice comment" in response.data

    # user2 cannot delete user1's comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.get("/delete-comment/1")
    assert response.status_code == 403
    response = client.get("/song/3/1?action=view")
    assert b"nice comment" in response.data

def test_cannot_edit_other_users_comment(client):
    create_user(client, "user1")
    create_user_and_song(client, "user2")

    # user1 comments on user2's song
    client.post("/login", data={"username": "user1", "password": "password"})
    client.post("/comment?threadid=3", data={"content": "mean comment"})
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

    # user2 cannot edit user1's rude comment
    client.post("/login", data={"username": "user2", "password": "password"})
    response = client.post("/comment?threadid=2&commentid=1", data={"content": "im a meanie"})
    assert response.status_code == 403
    response = client.get("/song/2/1?action=view")
    assert b"mean comment" in response.data

def test_comment_invalid_threadid(client):
    create_user_and_song(client)
    response = client.post("/comment?threadid=3", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?threadid=3")
    assert response.status_code == 404

def test_comment_invalid_replytoid(client):
    create_user_and_song(client)
    response = client.post("/comment?threadid=2&replytoid=1", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?threadid=2&replytoid=1")
    assert response.status_code == 404

def test_comment_invalid_commentid(client):
    create_user_and_song(client)
    response = client.post("/comment?threadid=2&commentid=1", data={"content": "broken comment"})
    assert response.status_code == 404

    response = client.get("/comment?threadid=2&commentid=1")
    assert response.status_code == 404

def test_comment_no_songid(client):
    create_user_and_song(client)
    response = client.post("/comment", data={"content": "broken comment"})
    assert response.status_code == 400

    response = client.get("/comment")
    assert response.status_code == 400

def test_delete_invalid_comment_id(client):
    create_user_and_song(client)
    response = client.get("/delete-comment/1")
    assert response.status_code == 404

