import enum

from . import db

def create_thread(threadtype, userid):
    thread = db.query("insert into comment_threads (threadtype, userid) values (?, ?) returning threadid", [threadtype, userid], one=True)
    db.commit()
    return thread["threadid"]

class ThreadType(enum.IntEnum):
    SONG = 0
    PROFILE = 1
    PLAYLIST = 2

