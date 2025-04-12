--DROP TABLE IF EXISTS jams;
CREATE TABLE jams (
    jamid INTEGER PRIMARY KEY,
    ownerid INTEGER NOT NULL,
    created TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(ownerid) REFERENCES users(userid)
);

--DROP TABLE IF EXISTS jam_events;
CREATE TABLE jam_events(
    eventid INTEGER PRIMARY KEY,
    jamid INTEGER NOT NULL,
    threadid INTEGER NOT NULL,
    created TEXT NOT NULL,
    title TEXT NOT NULL, -- Hidden until startdate
    startdate TEXT,
    enddate TEXT,
    description TEXT, -- Hidden until startdate
    FOREIGN KEY(jamid) REFERENCES jams(jamid),
    FOREIGN KEY(threadid) REFERENCES comment_threads(threadid)
);

ALTER TABLE songs ADD COLUMN eventid INTEGER REFERENCES jam_events(eventid);
CREATE INDEX idx_songs_by_eventid ON songs(eventid);

PRAGMA user_version = 5;

