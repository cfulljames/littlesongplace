--DROP TABLE IF EXISTS jams;
CREATE TABLE jams (
    jamid INTEGER PRIMARY KEY,
    owner INTEGER NOT NULL,
    created TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(owner) REFERENCES users(userid)
);

--DROP TABLE IF EXISTS jam_events;
CREATE TABLE jam_events(
    eventid INTEGER PRIMARY KEY,
    jamid INTEGER NOT NULL,
    created TEXT NOT NULL,
    title TEXT NOT NULL,
    startdate TEXT NOT NULL,
    enddate TEXT NOT NULL,
    threadid INTEGER NOT NULL,
    description TEXT,
    FOREIGN KEY(jamid) REFERENCES jams(jamid),
    FOREIGN KEY(threadid) REFERENCES comment_threads(threadid)
);
