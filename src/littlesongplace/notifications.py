from urllib import request

def send_notification(topic, title, body, url):
    req = request.Request(f"https://ntfy.littlesong.place/{topic}", method="POST")
    data = body.encode()
    req.add_header("Title", title)
    req.add_header("Click", url)
    response = request.urlopen(req, data=data)
    response.read()  # Wait for response

