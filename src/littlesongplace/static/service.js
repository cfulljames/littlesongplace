
self.addEventListener("push", (event) => {
    if (event.data) {
        const data = event.data.json();
        event.waitUntil(self.registration.showNotification(data.title, {body: data.body}));
    }
});

self.addEventListener("pushsubscriptionchanged", (event) => {
    console.log("Subscription expired");
    event.waitUntil(
        self.registration.pushManager.subscribe({ userVisibleOnly: true })
        .then((subscription) => {
            console.log("Register new subscription");
            const subid = window.localStorage.getItem("subid");
            return fetch(`/push-notifications/update-subscription/${subid}`, {
                method: "post",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(subscription)
            });
        })
    );
});

// TODO: handle notificationclick event
