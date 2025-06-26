var m_allSongs = [];
var m_songIndex = 0;

// Play a new song from the list in the player
function play(event) {
    var songElement = event.target.closest(".song");

    // Update song queue with songs on current page
    m_allSongs = [];
    for (const element of document.getElementsByClassName("song")) {
        m_allSongs.push(element);
    }

    m_songIndex = m_allSongs.indexOf(songElement);
    showBigPlayer();
    playCurrentSong();
}

function playCurrentSong() {
    var song = m_allSongs[m_songIndex];
    var songData = JSON.parse(song.dataset.song);

    var audio = document.getElementById("player-audio");
    audio.pause();
    audio.src = `/song/${songData.userid}/${songData.songid}`;
    audio.currentTime = 0;
    audio.play();

    var pfp = document.getElementById("player-pfp")
    var albumImg;
    if (songData.user_has_pfp) {
        pfp.style.display = "inline-block";
        pfp.src = `/pfp/${songData.userid}`;
        albumImg = `/pfp/${songData.userid}`;
    }
    else {
        pfp.style.display = "none";
        albumImg = "/static/lsp_notes.png";
    }

    var title = document.getElementById("player-title");
    title.textContent = songData.title;
    title.href = `/song/${songData.userid}/${songData.songid}?action=view`;

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
            link.classList.add("profile-link");
            link.textContent = collabname;
            collabs.appendChild(link);
        }
        else {
            var name = document.createElement("span");
            name.textContent = " " + collaborators[i];
            collabs.appendChild(name);
        }
    }

    // Copy song info to mini player
    document.getElementById("mini-player-title").textContent = songData.title;
    document.getElementById("mini-player-title").href = title.href;
    document.getElementById("mini-player-artist").textContent = songData.username;
    document.getElementById("mini-player-artist").href = artist.href;
    document.getElementById("mini-player-collabs").innerHTML = collabs.innerHTML;

    if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: songData.title,
            artist: songData.username,
            album: "Little Song Place",
            artwork: [{src: albumImg}],
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

function showBigPlayer() {
    document.getElementById("mini-player").hidden = true;
    document.getElementById("player").hidden = false;
}

function showMiniPlayer(event) {
    // Only show mini player if big player is already shown
    var bigPlayer = document.getElementById("player");
    if (!bigPlayer.hidden) {
        bigPlayer.hidden = true;
        document.getElementById("mini-player").hidden = false;
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
    if (m_songIndex == 0) {
        document.getElementById("player-audio").pause();
    }
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
    var position = document.getElementById("position-slider");
    if (audio.duration) {
        position.value = audio.currentTime / audio.duration;
    }
    else {
        position.value = 0;
    }

    document.getElementById("player-current-time").textContent = getTimeString(audio.currentTime);
    document.getElementById("player-total-time").textContent = getTimeString(audio.duration);
}

// Add event listeners
var m_firstLoadPlayer = true;
document.addEventListener("DOMContentLoaded", (event) => {

    // Sync volume with current slider position (may be reset after refresh)
    var audio = document.getElementById("player-audio");
    const slider = document.getElementById("volume-slider");
    audio.volume = slider.value;

    // The player never gets rebuilt, so we only need to set it up the first time
    if (!m_firstLoadPlayer) {
        return;
    }
    m_firstLoadPlayer = false;

    // Audio playback position while playing
    audio.addEventListener("timeupdate", songUpdate);

    // Next song on audio playback end
    audio.addEventListener("ended", songNext);

    // Show pause button when audio is playing
    var button = document.getElementById("play-pause-button");
    var miniButton = document.getElementById("mini-play-pause-button");
    audio.addEventListener("play", (event) => {
        button.className = "lsp_btn_pause02";
        button.src = customImage(document.getElementById("lsp_btn_pause02"), button);
        miniButton.className = "lsp_btn_pause02";
        miniButton.src = customImage(document.getElementById("lsp_btn_pause02"), button);
    })

    // Show play button when audio is paused
    audio.addEventListener("pause", (event) => {
        button.className = "lsp_btn_play02";
        button.src = customImage(document.getElementById("lsp_btn_play02"), button);
        miniButton.className = "lsp_btn_play02";
        miniButton.src = customImage(document.getElementById("lsp_btn_play02"), button);
    })

    // Audio position scrubbing
    document.getElementById("position-slider").oninput = function(event) {
        audio.currentTime = audio.duration * event.target.value;
    }

    // Use arrow keys for song position
    document.addEventListener("keydown", (event) => {
        if (["TEXTAREA", "INPUT"].includes(event.originalTarget.tagName)) {
            return;  // Only handle key presses if no other element is selected
        }
        var newTime = audio.currentTime;
        switch (event.key) {
            case "ArrowLeft":
                newTime -= 10;
                break;
            case "ArrowRight":
                newTime += 10;
                break;
            default:
                // Unhandled key - just ignore it
                return;
        }
        if (newTime < 0) {
            newTime = 0;
        }
        else if (newTime > audio.duration) {
            newTime = audio.duration;
        }
        audio.currentTime = newTime;
    });

    // Volume
    document.getElementById("volume-slider").oninput = function(event) {
        audio.volume = event.target.value;
    }

    // Show mini player on scroll
    document.addEventListener("scroll", showMiniPlayer);
});

