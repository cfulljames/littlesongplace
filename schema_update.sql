-- Add comment thread to songs table
ALTER TABLE songs ADD COLUMN threadid INTEGER;

-- Add profile comment thread to users table
ALTER TABLE users ADD COLUMN threadid INTEGER;

-- Add playlist comment thread to playlists table
ALTER TABLE playlists ADD COLUMN threadid INTEGER;

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

