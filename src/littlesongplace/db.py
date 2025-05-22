import sqlite3
from pathlib import Path

import click
from flask import abort, g, current_app

from . import datadir

DB_VERSION = 6

def get():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(datadir.get_db_path())
        db.cursor().execute("PRAGMA foreign_keys = ON")
        db.row_factory = sqlite3.Row

        # Get current version
        user_version = query("pragma user_version", one=True)[0]

        # Run update script if DB is out of date
        schema_update_script = Path(current_app.root_path) / 'sql' / 'schema_update.sql'
        if user_version < DB_VERSION and schema_update_script.exists():
            with current_app.open_resource(schema_update_script, mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()
    return db

def close(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query(query, args=(), one=False, expect_one=False):
    cur = get().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    if expect_one and not rv:
        abort(404)  # Not found

    return (rv[0] if rv else None) if (one or expect_one) else rv

def commit():
    get().commit()

@click.command("init-db")
def init_cmd():
    """Clear the existing data and create new tables"""
    with current_app.app_context():
        db = sqlite3.connect(datadir.get_db_path())
        with current_app.open_resource('sql/schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

@click.command("revert-db")
def revert_cmd():
    """Revert the database to the previous schema"""
    with current_app.app_context():
        db = sqlite3.connect(datadir.get_db_path())
        with current_app.open_resource('sql/schema_revert.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

def init_app(app):
    app.cli.add_command(init_cmd)
    app.cli.add_command(revert_cmd)
    app.teardown_appcontext(close)

