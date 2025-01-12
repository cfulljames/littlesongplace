var m_allSongs = [];
var m_songIndex = 0;

// Play a new song from the list in the player
function play(event) {
    var song = event.target.parentElement.parentElement.parentElement;
    m_songIndex = m_allSongs.indexOf(song);
    playCurrentSong();
}

function playCurrentSong() {
    var song = m_allSongs[m_songIndex];
    console.log(song);
    var songData = JSON.parse(song.dataset.song);

    var audio = document.getElementById("player-audio");
    audio.pause();
    audio.src = `/song/${songData.userid}/${songData.songid}`;
    audio.currentTime = 0;
    audio.play();

    var title = document.getElementById("player-title");
    title.textContent = songData.title;

    var separator = document.getElementById("player-info-sep");
    separator.hidden = false;

    var artist = document.getElementById("player-artist");
    artist.textContent = songData.username;
    artist.href = `/users/${songData.username}`;
    artist.hidden = false;
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

    // Audio position scrubbing
    var playerPosition = document.getElementById("player-position");
    playerPosition.addEventListener("mousedown", songScrub);
    playerPosition.addEventListener("mouseup", songScrub);
    playerPosition.addEventListener("mouseleave", songScrub);
    playerPosition.addEventListener("mousemove", songScrub);

    // Song play
    for (const element of document.getElementsByClassName("song-play-button")) {
        m_allSongs.push(element.parentElement.parentElement.parentElement);
        element.addEventListener("click", play);
    }
});

