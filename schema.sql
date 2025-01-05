DROP TABLE IF EXISTS users;
CREATE TABLE users (
    userid INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

DROP TABLE IF EXISTS songs;
CREATE TABLE songs (
    songid INTEGER PRIMARY KEY AUTOINCREMENT,
    userid INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(userid) REFERENCES users(userid)
);

DROP TABLE IF EXISTS song_collaborators;
CREATE TABLE song_collaborators (
    collabid INTEGER NOT NULL,
    songid INTEGER NOT NULL,
    userid INTEGER,
    name TEXT,
    FOREIGN KEY(userid) REFERENCES users(userid),
    PRIMARY KEY(collabid, songid),
    CONSTRAINT userid_or_name CHECK ((userid IS NULL and name IS NOT NULL) OR (userid IS NOT NULL and name IS NULL))
);

DROP TABLE IF EXISTS song_tags;
CREATE TABLE song_tags (
    tag TEXT NOT NULL,
    songid INTEGER NOT NULL,
    FOREIGN KEY(songid) REFERENCES songs(songid),
    PRIMARY KEY(tag, songid)
);
