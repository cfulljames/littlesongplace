var m_allSongs = [];
var m_songIndex = 0;

// Play a new song from the list in the player
function play(event) {
    var songElement = event.target;
    while (!songElement.classList.contains("song"))
    {
        songElement = songElement.parentElement;
    }
    m_songIndex = m_allSongs.indexOf(songElement);
    playCurrentSong();
}

function playCurrentSong() {
    var song = m_allSongs[m_songIndex];
    var songData = JSON.parse(song.dataset.song);

    var player = document.getElementById("player")
    player.hidden = false;

    var audio = document.getElementById("player-audio");
    audio.pause();
    audio.src = `/song/${songData.userid}/${songData.songid}`;
    audio.currentTime = 0;
    audio.play();

    var pfp = document.getElementById("player-pfp")
    pfp.style.display = "inline-block";
    pfp.src = `/pfp/${songData.userid}`

    var title = document.getElementById("player-title");
    title.textContent = songData.title;

    var separator = document.getElementById("player-info-sep");
    separator.hidden = false;

    var artist = document.getElementById("player-artist");
    artist.textContent = songData.username;
    artist.href = `/users/${songData.username}`;
    artist.hidden = false;

    var collabs = document.getElementById("player-collabs");
    collabs.textContent = "";

    var collaborators = songData.collaborators;
    for (i = 0; i < collaborators.length; i ++) {
        if (collaborators[i].startsWith("@")) {
            var collabname = collaborators[i].substr(1, collaborators[i].length - 1);
            var link = document.createElement("a");
            link.href = `/users/${collabname}`;
            link.classList.add("profile-link")
            link.textContent = collabname;
            collabs.appendChild(link);
        }
        else {
            var name = document.createElement("span");
            name.textContent = " " + collaborators[i];
            collabs.appendChild(name);
        }
    }

    //collabs.textContent = songData.collaborators.join(", ")


    if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: songData.title,
            artist: songData.username,
            album: "Little Song Place",
            artwork: [{src: "/static/lsp_notes.png"}],
        });
        navigator.mediaSession.setActionHandler('nexttrack', () => {
            songNext();
        });

        navigator.mediaSession.setActionHandler('previoustrack', () => {
            songPrevious();
        });

        navigator.mediaSession.setActionHandler('play', async () => {
            songPlayPause();
        });

        navigator.mediaSession.setActionHandler('pause', () => {
            songPlayPause();
        });
    }
}

// Play or pause the current song in the player
function songPlayPause() {
    var audio = document.getElementById("player-audio");
    if (audio.paused) {
        audio.play();
    }
    else {
        audio.pause();
    }
}

// Play the next song in the queue
function songNext() {
    m_songIndex = (m_songIndex + 1) % m_allSongs.length;
    playCurrentSong();
}

// Play the previous song in the queue
function songPrevious() {
    m_songIndex = m_songIndex - 1;
    if (m_songIndex < 0) {
        m_songIndex = m_allSongs.length - 1;
    }
    playCurrentSong();
}

// Convert float seconds to "min:sec"
function getTimeString(time) {
    if (isNaN(time))
    {
        time = 0.0;
    }
    var minute = Math.floor(time / 60);
    var second = Math.floor(time % 60);
    var secondStr = second.toString();
    if (secondStr.length < 2) {
        secondStr = "0" + secondStr;
    }
    return `${minute}:${secondStr}`;
}

// Update the player while the song plays
function songUpdate() {
    var audio = document.getElementById("player-audio");
    var bar = document.getElementById("player-position-bar");
    var dot = document.getElementById("player-position-dot");
    var songProgress = audio.currentTime / audio.duration;
    var maxPosition = bar.offsetWidth - dot.offsetWidth
    var dotPosition = songProgress * maxPosition;

    dot.style.left = `${dotPosition}px`;
    dot.style.visibility = "visible";

    document.getElementById("player-current-time").textContent = getTimeString(audio.currentTime);
    document.getElementById("player-total-time").textContent = getTimeString(audio.duration);
}

// Mouse scrub state
var m_isScrubbing = false;
var m_scrubPosition = 0;

// Handle a mouse event that scrubs the song position
function songScrub(event) {
    var audio = document.getElementById("player-audio");
    var bar = document.getElementById("player-position-bar");
    var dot = document.getElementById("player-position-dot");
    var maxPosition = bar.offsetWidth - dot.offsetWidth
    if (event.type == "mousedown") {
        // Start scrub
        m_isScrubbing = true;
        if (event.target === dot) {
            // Clicked dot - start scrub, but don't move yet
            var songProgress = audio.currentTime / audio.duration;
            m_scrubPosition = songProgress * maxPosition;
        }
        else {
            // Clicked outside of dot, set dot position immediately
            var dotPosition = event.offsetX - (dot.offsetWidth / 2);
            updateScrubPosition(dot, audio, dotPosition, maxPosition);
        }
    }
    else if (["mouseup", "mouseleave"].includes(event.type)) {
        // End scrub
        m_isScrubbing = false;
    }
    else if (event.type == "mousemove" && m_isScrubbing) {
        // Scrub
        var dotPosition = m_scrubPosition + event.movementX;
        updateScrubPosition(dot, audio, dotPosition, maxPosition);
    }

    // Prevent drag event from being used for selection
    if (event.stopPropagation) event.stopPropagation();
    if (event.preventDefault) event.preventDefault();
    event.cancelBubble = true;
    event.returnValue = false;
}

// Update scrub dot position
function updateScrubPosition(dot, audio, dotPosition, maxPosition) {
    if (dotPosition < 0) { dotPosition = 0; }
    if (dotPosition > maxPosition) { dotPosition = maxPosition; }
    dot.style.left = `${dotPosition}px`;
    m_scrubPosition = dotPosition;
    audio.currentTime = audio.duration * (dotPosition / maxPosition);
}

// Add event listeners
document.addEventListener("DOMContentLoaded", (event) => {

    // Audio playback position while playing
    var audio = document.getElementById("player-audio");
    audio.addEventListener("timeupdate", songUpdate);

    // Next song on audio playback end
    audio.addEventListener("ended", songNext);

    // Show pause button when audio is playing
    var button = document.getElementById("play-pause-button");
    audio.addEventListener("play", (event) => {
        button.src = "/static/lsp_btn_pause02.gif";
    })

    // Show play button when audio is paused
    audio.addEventListener("pause", (event) => {
        button.src = "/static/lsp_btn_play02.gif";
    })

    // Audio position scrubbing
    var playerPosition = document.getElementById("player-position");
    playerPosition.addEventListener("mousedown", songScrub);
    playerPosition.addEventListener("mouseup", songScrub);
    playerPosition.addEventListener("mouseleave", songScrub);
    playerPosition.addEventListener("mousemove", songScrub);

    // Song queue
    for (const element of document.getElementsByClassName("song")) {
        m_allSongs.push(element);
    }

    // Volume
    var vol = document.getElementById("volume-slider");
    vol.oninput = function() {
        console.log("updateVolume", vol);
        audio.volume = vol.value;
    }

});

