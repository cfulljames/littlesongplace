from flask import Blueprint, render_template

bp = Blueprint("jams", __name__, url_prefix="/jams")

@bp.get("/<int:jamid>")
def jam(jamid):
    return render_template("jam.html")
