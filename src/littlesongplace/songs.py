import json
from datetime import datetime
from dataclasses import dataclass

from . import comments, db, users
from .sanitize import sanitize_user_text

@dataclass
class Song:
    songid: int
    userid: int
    threadid: int
    username: str
    title: str
    description: str
    created: str
    tags: list[str]
    collaborators: list[str]
    user_has_pfp: bool

    def json(self):
        return json.dumps(vars(self))

    def get_comments(self):
        return comments.for_thread(self.threadid)

    @classmethod
    def by_id(cls, songid):
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songid = ?", [songid])
        if not songs:
            raise ValueError(f"No song for ID {songid:d}")

        return songs[0]

    @classmethod
    def by_threadid(cls, threadid):
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songs.threadid = ?", [threadid])
        if not songs:
            raise ValueError(f"No song for Thread ID {songid:d}")

        return songs[0]

    @classmethod
    def get_all_for_userid(cls, userid):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid where songs.userid = ? order by songs.created desc", [userid])

    @classmethod
    def get_all_for_username(cls, username):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid where users.username = ? order by songs.created desc", [username])

    @classmethod
    def get_all_for_username_and_tag(cls, username, tag):
        return cls._from_db(f"select * from song_tags inner join songs on song_tags.songid = songs.songid inner join users on songs.userid = users.userid where (username = ? and tag = ?) order by songs.created desc", [username, tag])

    @classmethod
    def get_all_for_tag(cls, tag):
        return cls._from_db(f"select * from song_tags inner join songs on song_tags.songid = songs.songid inner join users on songs.userid = users.userid where (tag = ?) order by songs.created desc", [tag])

    @classmethod
    def get_latest(cls, count):
        return cls._from_db("select * from songs inner join users on songs.userid = users.userid order by songs.created desc limit ?", [count])

    @classmethod
    def get_random(cls, count):
        # Get random songs + 10 extras so I can filter out my own (I uploaded too many :/)
        songs = cls._from_db("select * from songs inner join users on songs.userid = users.userid where songid in (select songid from songs order by random() limit ?)", [count + 10])
        random.shuffle(songs)

        # Prevent my songs from showing up in the first 10 results
        for i in reversed(range(min(10, len(songs)))):
            if songs[i].username == "cfulljames":
                del songs[i]

        # Drop any extra songs (since we asked for 10 extras)
        songs = songs[:count]

        return songs

    @classmethod
    def get_for_playlist(cls, playlistid):
        return cls._from_db("""\
            select * from playlist_songs
            inner join songs on playlist_songs.songid = songs.songid
            inner join users on songs.userid = users.userid
            where playlistid = ?
            order by playlist_songs.position asc
            """, [playlistid])

    @classmethod
    def _from_db(cls, query, args=()):
        songs_data = db.query(query, args)
        tags, collabs = cls._get_info_for_songs(songs_data)
        songs = []
        for sd in songs_data:
            song_tags = [t["tag"] for t in tags[sd["songid"]] if t["tag"]]
            song_collabs = [c["name"] for c in collabs[sd["songid"]] if c["name"]]
            created = datetime.fromisoformat(sd["created"]).astimezone().strftime("%Y-%m-%d")
            has_pfp = users.user_has_pfp(sd["userid"])
            songs.append(cls(sd["songid"], sd["userid"], sd["threadid"], sd["username"], sd["title"], sanitize_user_text(sd["description"]), created, song_tags, song_collabs, has_pfp))
        return songs

    @classmethod
    def _get_info_for_songs(cls, songs):
        tags = {}
        collabs = {}
        for song in songs:
            songid = song["songid"]
            tags[songid] = db.query("select (tag) from song_tags where songid = ?", [songid])
            collabs[songid] = db.query("select (name) from song_collaborators where songid = ?", [songid])
        return tags, collabs

