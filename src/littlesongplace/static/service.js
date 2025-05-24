
self.addEventListener("push", (event) => {
    if (event.data) {
        const data = event.data.json();
        event.waitUntil(self.registration.showNotification(data.title, {body: data.body}));
    }
});

// TODO: handle notificationclick event
