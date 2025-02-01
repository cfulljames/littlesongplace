ALTER TABLE users ADD COLUMN activitytime TEXT;

CREATE INDEX idx_songs_by_user ON songs(userid);

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

CREATE TABLE song_comment_notifications (
    notificationid INTEGER PRIMARY KEY,
    commentid INTEGER NOT NULL,
    targetuserid INTEGER NOT NULL,
    FOREIGN KEY(commentid) REFERENCES song_comments(commentid) ON DELETE CASCADE,
    FOREIGN KEY(targetuserid) REFERENCES users(userid) ON DELETE CASCADE
);
CREATE INDEX idx_song_comment_notifications_by_target ON song_comment_notifications(targetuserid);

PRAGMA user_version = 1;

