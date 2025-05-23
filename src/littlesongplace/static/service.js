self.addEventListener("activate", async () => {
    try {
        // TODO: Use VAPID key
        const options = {};
        const subscription = await self.registration.pushManager.subscribe(options);
        console.log(JSON.stringify(subscription));
        const response = await fetch(
            "/push-notifications/subscribe", {
                method: "post",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(subscription)
            }
        );
        console.log(response);
    }
    catch (err) {
        console.log("Error while activating service:", err);
    }

});

self.addEventListener("push", (event) => {
    if (event.data) {
        const data = event.data.json();
        event.waitUntil(self.registration.showNotification(data.title, {body: data.body}));
    }
});

// TODO: handle notificationclick event
