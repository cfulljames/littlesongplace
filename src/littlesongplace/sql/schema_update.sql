-- DROP TABLE IF EXISTS users_push_subscriptions
CREATE TABLE users_push_subscriptions (
    userid INTEGER NOT NULL,
    subscription TEXT NOT NULL,
    FOREIGN KEY(userid) REFERENCES users(userid) ON DELETE CASCADE
);

PRAGMA user_version = 6;
