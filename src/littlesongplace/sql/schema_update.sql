CREATE VIEW songs_view AS
    WITH
        tags_agg AS (
            SELECT songid, GROUP_CONCAT(tag) as tags
            FROM song_tags
            GROUP BY songid
        ),
        collaborators_agg AS (
            SELECT songid, GROUP_CONCAT(name) as collaborators
            FROM song_collaborators
            GROUP BY songid
        )
    SELECT
        songs.*,
        users.username,
        users.fgcolor,
        users.bgcolor,
        users.accolor,
        jam_events.title AS event_title,
        jam_events.jamid AS jamid,
        jam_events.enddate AS event_enddate,
        tags_agg.tags,
        collaborators_agg.collaborators
    FROM songs
    INNER JOIN users ON songs.userid = users.userid
    LEFT JOIN tags_agg ON tags_agg.songid = songs.songid
    LEFT JOIN collaborators_agg ON collaborators_agg.songid = songs.songid
    LEFT JOIN jam_events ON jam_events.eventid = songs.eventid;

PRAGMA user_version = 6;

