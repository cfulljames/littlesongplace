import uuid
from dataclasses import dataclass

from . import colors, datadir, db

@dataclass
class User:
    userid: int
    username: str
    fgcolor: str
    bgcolor: str
    accolor: str
    _ntfy_uuid: str

    @property
    def colors(self):
        return {
            "fgcolor": self.fgcolor,
            "bgcolor": self.bgcolor,
            "accolor": self.accolor,
        }

    @property
    def ntfy_uuid(self):
        if not self._ntfy_uuid:
            self._ntfy_uuid = str(uuid.uuid4())
            db.query(
                    "UPDATE users SET ntfyuuid = ? WHERE userid = ?",
                    [self._ntfy_uuid, self.userid])
            db.commit()
        return self._ntfy_uuid

    @classmethod
    def from_row(cls, row):
        user_colors = get_user_colors(row)
        return User(
                userid=row["userid"],
                username=row["username"],
                _ntfy_uuid=row["ntfyuuid"],
                **user_colors)

def by_id(userid):
    user_data = db.query("select * from users where userid = ?", [userid], one=True)
    return User.from_row(user_data)

def user_has_pfp(userid):
    return (datadir.get_user_images_path(userid)/"pfp.jpg").exists()

def get_user_colors(user_data):
    if isinstance(user_data, int):
        # Get colors for userid
        user_data = db.query("select * from users where userid = ?", [user_data], one=True)
    elif isinstance(user_data, str):
        # Get colors for username
        user_data = db.query("select * from users where username = ?", [user_data], one=True)

    user_colors = colors.DEFAULT_COLORS.copy()
    for key in user_colors:
        if user_data and user_data[key]:
            user_colors[key] = user_data[key]

    return user_colors

