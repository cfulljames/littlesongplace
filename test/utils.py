HOST = "http://littlesong.place:8000"

def url(path):
    return HOST + path

def login(session, username, password):
    session.post(url("/signup"), data={"username": username, "password": password, "password_confirm": password})
    response = session.post(url("/login"), data={"username": username, "password": password})
    response.raise_for_status()

