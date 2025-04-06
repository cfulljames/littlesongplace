import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
import littlesongplace as lsp

import bcrypt
import requests
import pytest

pytest.register_assert_rewrite("test.utils")

from .utils import login

fresh_db = None

@pytest.fixture
def app():
    global fresh_db
    # Use temporary data directory
    with tempfile.TemporaryDirectory() as data_dir:
        lsp.datadir.set_data_dir(data_dir)

        # Initialize Database
        with lsp.app.app_context():
            if fresh_db:
                # Already cached a fresh database file, just reuse it
                with open(lsp.datadir.get_db_path(), "wb") as dbfile:
                    dbfile.write(fresh_db)
            else:
                # No fresh db cached, create a new one (first test)
                db = sqlite3.connect(lsp.datadir.get_db_path())
                with lsp.app.open_resource('sql/schema.sql', mode='r') as f:
                    db.cursor().executescript(f.read())
                db.commit()
                db.close()

                # Cache database file
                with open(lsp.datadir.get_db_path(), "rb") as dbfile:
                    fresh_db = dbfile.read()

        yield lsp.app

@pytest.fixture
def client(app):
    # Mock bcrypt to speed up tests
    with patch.object(bcrypt, "hashpw", lambda passwd, salt: passwd), \
        patch.object(bcrypt, "checkpw", lambda passwd, saved: passwd == saved):
        yield app.test_client()

@pytest.fixture(scope="module")
def session():
    session = requests.Session()
    # User may already exist, but that's fine - we'll just ignore the signup error
    login(session, "user", "1234asdf!@#$")
    yield session

def pytest_addoption(parser):
    parser.addoption("--yt", action="store_true", help="run youtube importer tests")

def pytest_collection_modifyitems(config, items):
    if not config.option.yt:
        removed_items = [i for i in items if "yt" in i.keywords]
        for ri in removed_items:
            items.remove(ri)
        config.hook.pytest_deselected(items=removed_items)

