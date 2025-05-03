# Poll the artist text file (from the 'tuna' plugin), and if the artist name
# changed, fetch the new artist's colors from little song place, and update
# the visualizer.
#
# This is pretty specific to my OBS setup, but I figured I'd post it here in
# case anyone was curious how it works.

import re

import obspython as obs
import requests

prev_username = ""

def script_load(settings):
    obs.timer_add(update_colors_if_artist_changed, 1000)

def script_unload():
    obs.timer_remove(update_colors_if_artist_changed)

def update_colors_if_artist_changed():
    global prev_username

    # Get OBS source settings for visualizer sources
    artist = obs.obs_get_source_by_name("Artist")
    artist_settings = obs.obs_source_get_settings(artist)

    title = obs.obs_get_source_by_name("Title")
    title_settings = obs.obs_source_get_settings(title)

    vis = obs.obs_get_source_by_name("Visualizer")
    vis_settings = obs.obs_source_get_settings(vis)

    # Get the username from the artist file (created by the tuna plugin)
    filename = obs.obs_data_get_string(artist_settings, "file")
    with open(filename, "r") as artist_file:
        username = artist_file.read()

    try:
        if prev_username != username:
            # Username changed - get user colors for new username
            prev_username = username
            response = requests.get(f"https://littlesong.place/users/{username}")

            match = re.search(r'<div class="main" id="main" data-bgcolor="#(\w+)" data-fgcolor="#(\w+)" data-accolor="#(\w+)" data-username="">', response.text)
            if match:
                # Get colors, add alpha channel, and swap endianness (since OBS uses ABGR instead of RGBA)
                bgcolor, fgcolor, accolor = [bytearray.fromhex(g) + b"\xFF" for g in match.groups(0)]
                bgcolor = int.from_bytes(bgcolor, "little")
                fgcolor = int.from_bytes(fgcolor, "little")
                accolor = int.from_bytes(accolor, "little")

                # Use accent color for artist
                obs.obs_data_set_int(artist_settings, "color", accolor)
                obs.obs_source_update(artist, artist_settings)

                # Use foreground color for title
                obs.obs_data_set_int(title_settings, "color", fgcolor)
                obs.obs_source_update(title, title_settings)

                # Use background color for visualizer
                obs.obs_data_set_int(vis_settings, "color_base", bgcolor)
                obs.obs_source_update(vis, vis_settings)

    finally:
        obs.obs_data_release(artist_settings)
        obs.obs_source_release(artist)

        obs.obs_data_release(title_settings)
        obs.obs_source_release(title)

        obs.obs_data_release(vis_settings)
        obs.obs_source_release(vis)

