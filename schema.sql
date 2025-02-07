DROP TABLE IF EXISTS users;
CREATE TABLE users (
    userid INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password BLOB NOT NULL,
    bio TEXT,
    activitytime TEXT
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
CREATE INDEX idx_songs_by_user ON songs(userid);

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
    FOREIGN KEY(songid) REFERENCES songs(songid) ON DELETE CASCADE,
    FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_comments_by_song ON song_comments(songid);
CREATE INDEX idx_comments_by_user ON song_comments(userid);
CREATE INDEX idx_comments_by_replyto ON song_comments(replytoid);
CREATE INDEX idx_comments_by_time ON song_comments(created);

DROP TABLE IF EXISTS song_comment_notifications;
CREATE TABLE song_comment_notifications (
    notificationid INTEGER PRIMARY KEY,
    commentid INTEGER NOT NULL,
    targetuserid INTEGER NOT NULL,
    FOREIGN KEY(commentid) REFERENCES song_comments(commentid) ON DELETE CASCADE,
    FOREIGN KEY(targetuserid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_song_comment_notifications_by_target ON song_comment_notifications(targetuserid);

PRAGMA user_version = 1;

