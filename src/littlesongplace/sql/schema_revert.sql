DROP INDEX idx_songs_by_eventid;
ALTER TABLE songs DROP COLUMN eventid;
DROP TABLE IF EXISTS jams;
DROP TABLE IF EXISTS jam_events;

PRAGMA user_version = 4;

