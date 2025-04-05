import os
from pathlib import Path

_data_dir = Path(os.environ["DATA_DIR"]) if "DATA_DIR" in os.environ else Path(".data").absolute()

# Make sure _data_dir exists
os.makedirs(_data_dir, exist_ok=True)

def get_db_path():
    return _data_dir / "database.db"

def set_data_dir(newdir):
    global _data_dir
    _data_dir = Path(newdir)

def get_user_songs_path(userid):
    userpath = _data_dir / "songs" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def get_user_images_path(userid):
    userpath = _data_dir / "images" / str(userid)
    if not userpath.exists():
        os.makedirs(userpath)
    return userpath

def get_app_log_path():
    return _data_dir / "app.log"

