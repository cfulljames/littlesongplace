CREATE VIEW songs_view AS
    SELECT
        songs.*,
        users.username,
        users.fgcolor,
        users.bgcolor,
        users.accolor,
        jam_events.title AS event_title,
        jam_events.jamid AS jamid,
        jam_events.enddate AS event_enddate,
        group_concat(song_tags.tag) AS tags,
        group_concat(song_collaborators.name) AS collaborators
    FROM songs
    INNER JOIN users ON songs.userid = users.userid
    LEFT JOIN song_tags ON song_tags.songid = songs.songid
    LEFT JOIN song_collaborators ON song_collaborators.songid = songs.songid
    LEFT JOIN jam_events ON jam_events.eventid = songs.eventid
    GROUP BY songs.songid;

PRAGMA user_version = 6;

