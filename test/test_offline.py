import html
import json
import re
from pathlib import Path

import pytest

from .utils import create_user, create_user_and_song, upload_song

TEST_DATA = Path(__file__).parent / "data"

################################################################################
# Song Lists (Profile/Homepage/Songs)
################################################################################

# Profile

def _get_song_list_from_page(client, url):
    response = client.get(url)
    matches = re.findall('data-song="(.*)">', response.data.decode())
    return [json.loads(html.unescape(m)) for m in matches]

def test_profile_songs_one_song(client):
    create_user_and_song(client)
    songs = _get_song_list_from_page(client, "/users/user")

    assert len(songs) == 1
    assert songs[0]["title"] == "song title"

def test_profile_songs_two_songs(client):
    create_user_and_song(client)
    upload_song(client, b"Success", title="title2")
    songs = _get_song_list_from_page(client, "/users/user")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "title2"
    assert songs[1]["title"] == "song title"

# Homepage

def test_homepage_songs_two_songs(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song2")

    songs = _get_song_list_from_page(client, "/")

    # Newest first (all songs)
    assert len(songs) == 2
    assert songs[0]["title"] == "song2"
    assert songs[0]["username"] == "user2"

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

# Songs by tag

def test_songs_by_tag_no_user(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1", tags="tag")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song2", tags="")
    upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?tag=tag")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "song3"
    assert songs[0]["username"] == "user2"

    # Song 2 not shown, no tag

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

def test_songs_by_tag_with_user(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1", tags="tag")
    upload_song(client, b"Success", user="user1", title="song2", tags="")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?tag=tag&user=user1")

    assert len(songs) == 1
    assert songs[0]["title"] == "song1"
    assert songs[0]["username"] == "user1"
    # Song 2 not shown, no tag; song 3 not shown, by different user

def test_songs_by_user(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1", tags="tag")
    upload_song(client, b"Success", user="user1", title="song2", tags="")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = _get_song_list_from_page(client, "/songs?user=user1")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "song2"
    assert songs[0]["username"] == "user1"

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

    # Song 3 not shown, by different user

def test_single_song(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1", tags="tag")

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

def create_user_song_and_comment(client, content):
    create_user_and_song(client)
    response = client.post("/comment?threadid=2", data={"content": content})
    assert response.status_code == 302
    assert response.headers["Location"] == "/" # No previous page, use homepage

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

################################################################################
# Comments - Auth Status and Errors
################################################################################

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

################################################################################
# Activity
################################################################################

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

################################################################################
# New Activity Status
################################################################################

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

################################################################################
# Playlists
################################################################################

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

def create_user_song_and_playlist(client, playlist_type="private"):
    create_user_and_song(client)
    client.post("/create-playlist", data={"name": "my playlist", "type": playlist_type})

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
    songs = _get_song_list_from_page(client, "/playlists/1")
    assert songs[0]["songid"] == 1
    assert songs[1]["songid"] == 2

    client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": "2,1"})
    songs = _get_song_list_from_page(client, "/playlists/1")
    assert songs[0]["songid"] == 2
    assert songs[1]["songid"] == 1

def test_edit_playlist_remove_song(client):
    create_user_song_and_playlist(client)
    upload_song(client, b"Successfully uploaded")
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "1"})
    client.post("/append-to-playlist", data={"playlistid": "1", "songid": "2"})
    songs = _get_song_list_from_page(client, "/playlists/1")
    assert len(songs) == 2

    client.post("/edit-playlist/1", data={"name": "my playlist", "type": "private", "songids": "2"})
    songs = _get_song_list_from_page(client, "/playlists/1")
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

