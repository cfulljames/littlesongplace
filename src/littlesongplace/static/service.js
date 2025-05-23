const vapid_public_key = "BLsO37LostwqKch7SFr5Df0MexEoBOcujdMRY7wJurRPc_MGdz9rAkMrqs_dil4qSFxVbVyAA3FqLEPSL-WRNZs";

self.addEventListener("activate", async () => {
    try {
        // Subscribe via browser's push service
        const options = {userVisibleOnly: true, applicationServerKey: vapid_public_key};
        const subscription = await self.registration.pushManager.subscribe(options);
        console.log(JSON.stringify(subscription));

        // Register subscription with LSP server
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
