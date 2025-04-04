from .utils import create_user_and_song, create_user, upload_song, get_song_list_from_page

# Profile ######################################################################

def test_profile_songs_one_song(client):
    create_user_and_song(client)
    songs = get_song_list_from_page(client, "/users/user")

    assert len(songs) == 1
    assert songs[0]["title"] == "song title"

def test_profile_songs_two_songs(client):
    create_user_and_song(client)
    upload_song(client, b"Success", title="title2")
    songs = get_song_list_from_page(client, "/users/user")

    # Newest first
    assert len(songs) == 2
    assert songs[0]["title"] == "title2"
    assert songs[1]["title"] == "song title"

# Homepage #####################################################################

def test_homepage_songs_two_songs(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song2")

    songs = get_song_list_from_page(client, "/")

    # Newest first (all songs)
    assert len(songs) == 2
    assert songs[0]["title"] == "song2"
    assert songs[0]["username"] == "user2"

    assert songs[1]["title"] == "song1"
    assert songs[1]["username"] == "user1"

# Songs by tag #################################################################

def test_songs_by_tag_no_user(client):
    create_user(client, "user1", "password", login=True)
    upload_song(client, b"Success", user="user1", title="song1", tags="tag")

    create_user(client, "user2", "password", login=True)
    upload_song(client, b"Success", user="user2", title="song2", tags="")
    upload_song(client, b"Success", user="user2", title="song3", tags="tag")

    songs = get_song_list_from_page(client, "/songs?tag=tag")

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

    songs = get_song_list_from_page(client, "/songs?tag=tag&user=user1")

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

    songs = get_song_list_from_page(client, "/songs?user=user1")

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

    songs = get_song_list_from_page(client, "/song/1/1?action=view")

    assert len(songs) == 1
    assert songs[0]["title"] == "song1"
    assert songs[0]["username"] == "user1"

