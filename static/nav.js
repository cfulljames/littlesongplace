document.addEventListener("DOMContentLoaded", (e) => {

    // Handle link clicks with AJAX
    document.querySelectorAll("a").forEach((anchor) => {
        anchor.removeEventListener("click", onLinkClick);
        anchor.addEventListener("click", onLinkClick);
    });

    // Handle form submissions with AJAX
    document.querySelectorAll("form").forEach((form) => {
        form.removeEventListener("submit", onFormSubmit);
        form.addEventListener("submit", onFormSubmit);
    });

    // Update colors
    var mainDiv = document.getElementById("main");
    var rootStyle = document.documentElement.style;
    rootStyle.setProperty("--yellow", mainDiv.dataset.bgcolor);
    rootStyle.setProperty("--black", mainDiv.dataset.fgcolor);
    rootStyle.setProperty("--purple", mainDiv.dataset.accolor);

    updateImageColors();

    // Update navbar based on logged-in status
    var username = mainDiv.dataset.username;
    var loggedIn = username ? true : false;
    document.querySelectorAll(".nav-logged-in").forEach((e) => {e.hidden = !loggedIn;});
    document.querySelectorAll(".nav-logged-out").forEach((e) => {e.hidden = loggedIn;});
    if (loggedIn) {
        document.getElementById("logged-in-status").innerText = `Signed in as ${username}`;
    }

    // Update activity indicator status
    checkForNewActivity();
});

function onLinkClick(event) {
    var targetUrl = new URL(event.currentTarget.href);
    if (urlIsOnSameSite(targetUrl)) {
        event.preventDefault();
        event.stopPropagation();
        fetch(targetUrl, {redirect: "follow"}).then(handleAjaxResponse);
    }
}

function onFormSubmit(event) {
    var targetUrl = new URL(event.target.action);
    if (urlIsOnSameSite(targetUrl)) {
        event.preventDefault();
        event.stopPropagation();
        var formData = new FormData(event.target);
        fetch(targetUrl, {redirect: "follow", body: formData, method: event.target.method})
            .then(handleAjaxResponse);
    }
}

function urlIsOnSameSite(targetUrl) {
    var currentUrl = new URL(window.location.href);
    return targetUrl.origin === currentUrl.origin;
}

async function handleAjaxResponse(response) {
    // Update URL in browser window, minus request-type field
    var url = new URL(response.url);
    url.searchParams.delete("request-type");

    // Get page content from XML response
    var text = await response.text();
    window.history.pushState(text, "", url);

    updatePageState(text);
}

// Populate page state from history stack when user navigates back
window.addEventListener("popstate", (event) => updatePageState(event.state));

function updatePageState(data) {
    // Replace the contents of the current page with those from data

    if (!data) {
        fetch(window.location.href, {redirect: "follow"}).then(handleAjaxResponse);
        return;
    }
    var parser = new DOMParser();
    data = parser.parseFromString(data, "text/html");

    // Update main body content
    var newMainDiv = data.getElementById("main");
    var oldMainDiv = document.getElementById("main");
    document.body.replaceChild(newMainDiv, oldMainDiv);

    // Update flashed messages
    var newFlashes = data.getElementById("flashes-container");
    var oldFlashes = document.getElementById("flashes-container");
    oldFlashes.parentElement.replaceChild(newFlashes, oldFlashes);

    // Update page title
    document.title = data.title;

    // Load inline scripts (DOMParser disables these by default)
    var scripts = document.getElementById("main").getElementsByTagName("script");
    for (const script of scripts) {
        var newScript = document.createElement("script");
        newScript.type = script.type;
        newScript.text = script.text;
        script.parentElement.replaceChild(newScript, script);
    }

    // Delete old color picker (will be recreated on DOMContentLoaded)
    document.getElementById("clr-picker").remove();

    // Trigger event to signal new page has loaded
    var event = new Event("DOMContentLoaded");
    document.dispatchEvent(event);
}

async function checkForNewActivity() {
    // Query the server to see if the user has new activity

    // Only check for activity if user is logged in
    var mainDiv = document.getElementById("main");
    var username = mainDiv.dataset.username;
    if (!username) {
        return;
    }

    // Logged in - make the activity status request
    const indicator = document.getElementById("activity-indicator")
    const response = await fetch("/new-activity");
    if (!response.ok) {
        console.log(`Failed to get activity: ${response.status}`);
    }
    const json = await response.json();
    indicator.hidden = !json.new_activity;
}

// Check for new activity every 10s
setInterval(checkForNewActivity, 10000);

function customImage(element) {
    // Customize an image by performing a palette swap on the .gif
    // file.  The source element must contain a data-img-b64 attribute
    // containing the base64 representation of a .gif file.  The byte
    // indexes match .gifs from Aseprite, and may not work for all
    // .gif files.

    var style = window.getComputedStyle(document.body);
    var bgcolor = style.getPropertyValue("--yellow");
    var accolor = style.getPropertyValue("--purple");

    // Convert base64 string to Uint8Array so we can modify it
    var data = atob(element.dataset.imgB64);
    var bytes = Uint8Array.from(data, c => c.charCodeAt(0));

    // Replace background color palette bytes in gif file
    bytes[16] = parseInt(bgcolor.substring(1, 3), 16);
    bytes[17] = parseInt(bgcolor.substring(3, 5), 16);
    bytes[18] = parseInt(bgcolor.substring(5, 7), 16);

    // Replace foreground color palette bytes in gif file
    bytes[19] = parseInt(accolor.substring(1, 3), 16);
    bytes[20] = parseInt(accolor.substring(3, 5), 16);
    bytes[21] = parseInt(accolor.substring(5, 7), 16);

    // Convert Uint8Array back to base64 so we can use it in a src string
    data = btoa(String.fromCharCode(...bytes));

    // Embed base64 in a data string that can be used as an img src.
    return `data:image/gif;base64, ${data}`;
}

function updateImageColors() {
    // Perform a palette swap on all gifs based on current page colors
    document.querySelectorAll(".img-data").forEach(e => {
        document.querySelectorAll(`.${e.id}`).forEach(t => {
            t.src = customImage(e);
        });
    });
}

