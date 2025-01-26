DROP TABLE IF EXISTS users;
CREATE TABLE users (
    userid INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password BLOB NOT NULL,
    bio TEXT
);
CREATE INDEX users_by_name ON users(username);

DROP TABLE IF EXISTS songs;
CREATE TABLE songs (
    songid INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    userid INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(userid) REFERENCES users(userid)
);

DROP TABLE IF EXISTS song_collaborators;
CREATE TABLE song_collaborators (
    songid INTEGER NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(songid) REFERENCES songs(songid),
    PRIMARY KEY(songid, name)
);

DROP TABLE IF EXISTS song_tags;
CREATE TABLE song_tags (
    songid INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY(songid) REFERENCES songs(songid),
    PRIMARY KEY(songid, tag)
);
CREATE INDEX idx_song_tags_tag ON song_tags(tag);

DROP TABLE IF EXISTS song_comments;
CREATE TABLE song_comments (
    commentid INTEGER PRIMARY KEY,
    songid INTEGER NOT NULL,
    userid INTEGER NOT NULL,
    replytoid INTEGER,
    created TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(songid) REFERENCES songs(songid),
    FOREIGN KEY(userid) REFERENCES users(userid)
);
CREATE INDEX idx_comments_by_song ON song_comments(songid);

