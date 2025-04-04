
def test_site_news(client):
    response = client.get("/site-news")
    assert response.status_code == 200
    assert b"Site News" in response.data
