HOST = "http://littlesong.place:8000"

def url(path):
    return HOST + path

def login(session, username, password):
    session.post(url("/signup"), data={"username": username, "password": password, "password_confirm": password})
    response = session.post(url("/login"), data={"username": username, "password": password})
    response.raise_for_status()

def post_signup_form(client, username, password, password_confirm=None):
    if password_confirm is None:
        password_confirm = password
    return client.post(
            "/signup",
            data=dict(username=username, password=password, password_confirm=password_confirm))

def create_user(client, username, password="password", login=False):
    response = post_signup_form(client, username, password)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    if login:
        response = client.post("/login", data={"username": username, "password": password})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/users/{username}"

