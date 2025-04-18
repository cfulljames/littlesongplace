DROP TABLE IF EXISTS users;
CREATE TABLE users (
    userid INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password BLOB NOT NULL,
    bio TEXT,
    activitytime TEXT,
    bgcolor TEXT,
    fgcolor TEXT,
    accolor TEXT,
    threadid INTEGER
);
CREATE INDEX users_by_name ON users(username);

DROP TABLE IF EXISTS songs;
CREATE TABLE songs (
    songid INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    userid INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    threadid INTEGER,
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
 
-- Old comment system (superceded by comments/comment_threads/comment_notifications
--
-- DROP TABLE IF EXISTS song_comments;
-- CREATE TABLE song_comments (
--     commentid INTEGER PRIMARY KEY,
--     songid INTEGER NOT NULL,
--     userid INTEGER NOT NULL,
--     replytoid INTEGER,
--     created TEXT NOT NULL,
--     content TEXT NOT NULL,
--     FOREIGN KEY(songid) REFERENCES songs(songid) ON DELETE CASCADE,
--     FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
-- );
-- CREATE INDEX idx_comments_by_song ON song_comments(songid);
-- CREATE INDEX idx_comments_by_user ON song_comments(userid);
-- CREATE INDEX idx_comments_by_replyto ON song_comments(replytoid);
-- CREATE INDEX idx_comments_by_time ON song_comments(created);
-- 
-- DROP TABLE IF EXISTS song_comment_notifications;
-- CREATE TABLE song_comment_notifications (
--     notificationid INTEGER PRIMARY KEY,
--     commentid INTEGER NOT NULL,
--     targetuserid INTEGER NOT NULL,
--     FOREIGN KEY(commentid) REFERENCES song_comments(commentid) ON DELETE CASCADE,
--     FOREIGN KEY(targetuserid) REFERENCES users(userid) ON DELETE CASCADE
-- );
-- CREATE INDEX idx_song_comment_notifications_by_target ON song_comment_notifications(targetuserid);

DROP TABLE IF EXISTS playlists;
CREATE TABLE playlists (
    playlistid INTEGER PRIMARY KEY,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    userid INTEGER NOT NULL,
    name TEXT NOT NULL,
    private INTEGER NOT NULL,
    threadid INTEGER,

    FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX playlists_by_userid ON playlists(userid);

DROP TABLE IF EXISTS playlist_songs;
CREATE TABLE playlist_songs (
    playlistid INTEGER NOT NULL,
    position INTEGER NOT NULL,
    songid INTEGER NOT NULL,

    PRIMARY KEY(playlistid, position),
    FOREIGN KEY(playlistid) REFERENCES playlists(playlistid) ON DELETE CASCADE,
    FOREIGN KEY(songid) REFERENCES songs(songid) ON DELETE CASCADE
);
CREATE INDEX playlist_songs_by_playlist ON playlist_songs(playlistid);

DROP TABLE IF EXISTS comment_threads;
CREATE TABLE comment_threads (
    threadid INTEGER PRIMARY KEY,
    threadtype INTEGER NOT NULL,
    userid INTEGER NOT NULL,
    FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
);

-- Delete comment thread when song deleted
CREATE TRIGGER trg_delete_song_comments
BEFORE DELETE ON songs FOR EACH ROW
BEGIN
    DELETE FROM comment_threads WHERE threadid = OLD.threadid;
END;

-- Delete comment thread when profile deleted
CREATE TRIGGER trg_delete_profile_comments
BEFORE DELETE ON users FOR EACH ROW
BEGIN
    DELETE FROM comment_threads WHERE threadid = OLD.threadid;
END;

-- Delete comment thread when playlist deleted
CREATE TRIGGER trg_delete_playlist_comments
BEFORE DELETE ON playlists FOR EACH ROW
BEGIN
    DELETE FROM comment_threads WHERE threadid = OLD.threadid;
END;

DROP TABLE IF EXISTS comments;
CREATE TABLE comments (
    commentid INTEGER PRIMARY KEY,
    threadid INTEGER NOT NULL,
    userid INTEGER NOT NULL,
    replytoid INTEGER,
    created TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(threadid) REFERENCES comment_threads(threadid) ON DELETE CASCADE,
    FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_comments_user ON comments(userid);
CREATE INDEX idx_comments_replyto ON comments(replytoid);
CREATE INDEX idx_comments_time ON comments(created);

DROP TABLE IF EXISTS notifications;
CREATE TABLE notifications (
    notificationid INTEGER PRIMARY KEY,
    objectid INTEGER NOT NULL,
    objecttype INTEGER NOT NULL,
    targetuserid INTEGER NOT NULL,
    created TEXT NOT NULL,
    FOREIGN KEY(targetuserid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_notifications_by_target ON notifications(targetuserid);
CREATE INDEX idx_notifications_by_object ON notifications(objectid);

-- Delete comment notifications when comment deleted
CREATE TRIGGER trg_delete_notifications
BEFORE DELETE ON comments FOR EACH ROW
BEGIN
    DELETE FROM notifications WHERE objectid = OLD.commentid AND objecttype = 0;
END;

PRAGMA user_version = 4;

