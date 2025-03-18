-- Create new comment tables
CREATE TABLE comment_threads (
    threadid INTEGER PRIMARY KEY,
    threadtype INTEGER DEFAULT 0,
);

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

CREATE TABLE comment_notifications (
    notificationid INTEGER PRIMARY KEY,
    commentid INTEGER NOT NULL,
    targetuserid INTEGER NOT NULL,
    FOREIGN KEY(commentid) REFERENCES comments(commentid) ON DELETE CASCADE,
    FOREIGN KEY(targetuserid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_comment_notifications_by_target ON comment_notifications(targetuserid);

-- Add comment thread to songs table
ALTER TABLE songs ADD COLUMN threadid INTEGER;

-- Add profile comment thread to users table
ALTER TABLE users ADD COLUMN threadid INTEGER;

-- Add playlist comment thread to playlists table
ALTER TABLE playlists ADD COLUMN threadid INTEGER;

PRAGMA user_version = 4;

