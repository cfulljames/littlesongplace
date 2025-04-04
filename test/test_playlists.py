from .utils import create_user, upload_song, get_song_list_from_page, create_user_song_and_playlist

# Create Playlist ##############################################################

def test_create_playlist(client):
    create_user(client, "user", login=True)
    response = client.post("/create-playlist", data={"name": "my playlist", "type": "private"})
    assert response.status_code == 302

    response = client.get("/users/user")
    assert b"my playlist" in response.data
    assert b"[Private]" in response.data

def test_create_playlist_invalid_name(client):
    create_user(client, "user", login=True)
    response = client.post("/create-playlist", data={"name": "a"*201, "type": "private"})
    assert response.status_code == 302
    response = client.get("/users/user")
    assert b"must have a name" in response.data

    response = client.post("/create-playlist", data={"name": "", "type": "private"})
    assert response.status_code == 302
    response = client.get("/users/user")
    assert b"must have a name" in response.data

def test_create_playlist_not_logged_in(client):
    response = client.post("/create-playlist", data={"name": "my playlist", "type": "private"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

# Delete Playlist ##############################################################

def create_user_and_playlist(client):
    create_user(client, "user", login=True)
    client.post("/create-playlist", data={"name": "my playlist", "type": "private"})

def test_delete_playlist(client):
    create_user_and_playlist(client)
    response = client.get("/delete-playlist/1", follow_redirects=True)
    assert b"Deleted playlist my playlist" in response.data

    response = client.get("/users/user")
    assert not b"my playlist" in response.data

def test_delete_playlist_invalid_playlistid(client):
    create_user_and_playlist(client)
    response = client.get("/delete-playlist/2")
    assert response.status_code == 404

def test_delete_playlist_not_logged_in(client):
    create_user_and_playlist(client)
    client.get("/logout")

    response = client.get("/delete-playlist/2")
    assert response.status_code == 401

def test_delete_playlist_other_users_playlist(client):
    create_user_and_playlist(client)
    create_user(client, "user2", login=True)

    response = client.get("/delete-playlist/1")
    assert response.status_code == 403

# Append to Playlist ###########################################################

def test_append_to_playlist(client):
    create_user_song_and_playlist(client)
    response = client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    data = response.json
    assert data["status"] == "success"
    assert "Added 'song title' to my playlist" in data["messages"]

def test_append_to_playlist_not_logged_in(client):
    create_user_song_and_playlist(client)
    client.get("/logout")
    response = client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    assert response.status_code == 401

def test_append_to_other_users_playlist(client):
    create_user_song_and_playlist(client)
    create_user(client, "user2", login=True)
    response = client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    assert response.status_code == 403

def test_append_playlist_invalid_songid(client):
    create_user_song_and_playlist(client)
    response = client.post("/append-to-playlist", data={"playlistid": "1", "songid": "2"})
    assert response.status_code == 404

def test_append_playlist_invalid_playlistid(client):
    create_user_song_and_playlist(client)
    response = client.post("/append-to-playlist", data={"playlistid": "2", "songid": "1"})
    assert response.status_code == 404

# Playlist on Profile ##########################################################

def test_playlists_on_own_profile(client):
    create_user_song_and_playlist(client)  # Private playlist
    client.post("/create-playlist", data={"name": "my public playlist", "type": "public"}, follow_redirects=True)
    client.get("/users/user") # Clear flashes

    # Shows public and private playlists
    response = client.get("/users/user")
    assert b"my playlist" in response.data
    assert b"my public playlist" in response.data

def test_playlists_on_other_users_profile(client):
    create_user_song_and_playlist(client)  # Private playlist
    client.post("/create-playlist", data={"name": "my public playlist", "type": "public"})
    client.get("/users/user") # Clear flashes

    # Shows only public playlists
    create_user(client, "user2", login=True)
    response = client.get("/users/user")
    assert b"my playlist" not in response.data
    assert b"my public playlist" in response.data

# View Playlist ################################################################

def test_view_own_public_playlist(client):
    create_user_song_and_playlist(client, playlist_type="public")
    response = client.get("/playlists/1")
    assert response.status_code == 200
    assert b"[Public]" in response.data

def test_view_own_private_playlist(client):
    create_user_song_and_playlist(client, playlist_type="private")
    response = client.get("/playlists/1")
    assert response.status_code == 200
    assert b"[Private]" in response.data

def test_view_other_users_public_playlist(client):
    create_user_song_and_playlist(client, playlist_type="public")
    create_user(client, "user2", login=True)
    response = client.get("/playlists/1")
    assert response.status_code == 200
    assert b"[Public]" not in response.data  # Type not shown

def test_view_other_users_private_playlist(client):
    create_user_song_and_playlist(client, playlist_type="private")
    create_user(client, "user2", login=True)
    response = client.get("/playlists/1")
    assert response.status_code == 404

def test_view_invalid_playlist(client):
    response = client.get("/playlists/0")
    assert response.status_code == 404

# Edit Playlist ################################################################

def test_edit_playlist_change_type(client):
    create_user_song_and_playlist(client, playlist_type="private")
    response = client.post("/edit-playlist/1", data={"name": "my playlist", "type": "public", "songids": ""})
    assert response.status_code == 302

    response = client.get("/playlists/1")
    assert b"[Public]" in response.data

def test_edit_playlist_change_name(client):
    create_user_song_and_playlist(client, playlist_type="private")
    response = client.post("/edit-playlist/1", data={"name": "cool new playlist name", "type": "private", "songids": ""})
    assert response.status_code == 302

    response = client.get("/playlists/1")
    assert b"cool new playlist name" in response.data

def test_edit_playlist_change_name_invalid(client):
    create_user_song_and_playlist(client, playlist_type="private")
    client.get("/playlists/1")  # Clear flashes
    response = client.post("/edit-playlist/1", data={"name": "", "type": "private", "songids": ""})
    assert response.status_code == 302

    response = client.get("/playlists/1")
    assert b"my playlist" in response.data
    assert b"must have a name" in response.data

def test_edit_playlist_change_song_order(client):
    create_user_song_and_playlist(client)
    upload_song(client, b"Successfully uploaded")
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "2"})
    songs = get_song_list_from_page(client, "/playlists/1")
    assert songs[0]["songid"] == 1
    assert songs[1]["songid"] == 2

    client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": "2,1"})
    songs = get_song_list_from_page(client, "/playlists/1")
    assert songs[0]["songid"] == 2
    assert songs[1]["songid"] == 1

def test_edit_playlist_remove_song(client):
    create_user_song_and_playlist(client)
    upload_song(client, b"Successfully uploaded")
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "2"})
    songs = get_song_list_from_page(client, "/playlists/1")
    assert len(songs) == 2

    client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": "2"})
    songs = get_song_list_from_page(client, "/playlists/1")
    assert len(songs) == 1
    assert songs[0]["songid"] == 2

def test_edit_playlist_not_logged_in(client):
    create_user_song_and_playlist(client)
    client.get("/logout")

    response = client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": ""})
    assert response.status_code == 401

def test_edit_other_users_playlist(client):
    create_user_song_and_playlist(client)
    create_user(client, "user2", login=True)

    response = client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": ""})
    assert response.status_code == 403

def test_edit_playlist_invalid_songid(client):
    create_user_and_playlist(client)
    response = client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": "1"})
    assert response.status_code == 400

def test_edit_playlist_invalid_playlistid(client):
    create_user_and_playlist(client)
    response = client.post("/edit-playlist/2", data={"name": "my playlist", "type": "private", "songids": ""})
    assert response.status_code == 404

