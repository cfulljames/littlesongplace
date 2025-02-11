CREATE TABLE playlists (
    playlistid INTEGER PRIMARY KEY,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    userid INTEGER NOT NULL,
    name TEXT NOT NULL,
    private INTEGER NOT NULL,

    FOREIGN KEY(userid) REFERENCES users(userid)
);

CREATE TABLE playlist_songs (
    playlistid INTEGER NOT NULL,
    position INTEGER NOT NULL,
    songid INTEGER NOT NULL,

    PRIMARY KEY(playlistid, position),
    FOREIGN KEY(playlistid) REFERENCES playlists(playlistid),
    FOREIGN KEY(songid) REFERENCES songs(songid)
);
CREATE INDEX playlist_songs_by_playlist ON playlist_songs(playlistid);

PRAGMA user_version = 3;

