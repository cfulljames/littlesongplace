from flask import abort, Blueprint, g, redirect, render_template, request, session, url_for

bp = Blueprint("swap-shop", __name__, url_prefix="/swap-shop")

@bp.get("/")
def view():
    participants = []
    recipient = None
    return render_template("swap-shop.html", participants=participants)

@bp.post("/enter")
def enter():
    session["swap-shop-name"] = request.form["name"]
    return redirect(url_for(view))

@bp.get("/start")
def start():
    return redirect(url_for(view))

@bp.post("/clear")
def clear():
    return redirect(url_for(view))

