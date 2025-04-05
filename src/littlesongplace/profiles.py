from flask import abort, Blueprint, current_app, flash, send_from_directory, redirect, render_template, request, session
from PIL import Image, UnidentifiedImageError

from . import comments, datadir, db, songs, users
from .sanitize import sanitize_user_text

bp = Blueprint("profiles", __name__)

@bp.get("/users/<profile_username>")
def users_profile(profile_username):

    # Look up user data for current profile
    profile_data = db.query("select * from users where username = ?", [profile_username], one=True)
    if profile_data is None:
        abort(404)
    profile_userid = profile_data["userid"]

    # Get playlists for current profile
    userid = session.get("userid", None)
    show_private = userid == profile_userid
    if show_private:
        plist_data = db.query("select * from playlists where userid = ? order by updated desc", [profile_userid])
    else:
        plist_data = db.query("select * from playlists where userid = ? and private = 0 order by updated desc", [profile_userid])

    # Get songs for current profile
    profile_songs = songs.Song.get_all_for_userid(profile_userid)

    # Get comments for current profile
    profile_comments = comments.for_thread(profile_data["threadid"])

    # Sanitize bio
    profile_bio = ""
    if profile_data["bio"] is not None:
        profile_bio = sanitize_user_text(profile_data["bio"])

    return render_template(
            "profile.html",
            name=profile_username,
            userid=profile_userid,
            bio=profile_bio,
            **users.get_user_colors(profile_data),
            playlists=plist_data,
            songs=profile_songs,
            comments=profile_comments,
            threadid=profile_data["threadid"],
            user_has_pfp=users.user_has_pfp(profile_userid))

@bp.post("/edit-profile")
def edit_profile():
    if not "userid" in session:
        abort(401)

    db.query(
            "update users set bio = ?, bgcolor = ?, fgcolor = ?, accolor = ? where userid = ?",
            [request.form["bio"], request.form["bgcolor"], request.form["fgcolor"], request.form["accolor"], session["userid"]])
    db.commit()

    if request.files["pfp"]:
        pfp_path = datadir.get_user_images_path(session["userid"]) / "pfp.jpg"

        try:
            with Image.open(request.files["pfp"]) as im:
                # Drop alpha channel
                if im.mode in ("RGBA", "P"):
                    im = im.convert("RGB")

                target_size = 256  # Square (same width/height)
                # Resize
                if im.width >= im.height:
                    scale = 256 / im.height
                else:
                    scale = 256 / im.width

                im = im.resize((round(im.width*scale), round(im.height*scale)))

                # Crop to square
                center_h = im.width / 2
                center_v = im.height / 2
                left = center_h - (target_size // 2)
                right = center_h + (target_size // 2)
                top = center_v - (target_size // 2)
                bottom = center_v + (target_size // 2)
                im = im.crop((left, top, right, bottom))

                # Save to permanent location
                im.save(pfp_path)
        except UnidentifiedImageError:
            abort(400)  # Invalid image

    flash("Profile updated successfully")

    current_app.logger.info(f"{session['username']} updated bio")

    return redirect(f"/users/{session['username']}")

@bp.get("/pfp/<int:userid>")
def pfp(userid):
    return send_from_directory(datadir.get_user_images_path(userid), "pfp.jpg")

