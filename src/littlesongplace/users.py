from dataclasses import dataclass

from . import colors, datadir, db

@dataclass
class User:
    userid: int
    username: str
    fgcolor: str
    bgcolor: str
    accolor: str

    @property
    def colors(self):
        return {
            "fgcolor": self.fgcolor,
            "bgcolor": self.bgcolor,
            "accolor": self.accolor,
        }

    @classmethod
    def from_row(cls, row):
        user_colors = get_user_colors(row)
        return User(
                userid=row["userid"],
                username=row["username"],
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

