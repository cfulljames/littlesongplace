import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
import littlesongplace as lsp

import bcrypt
import requests
import pytest

from .utils import login

@pytest.fixture
def app():
    # Use temporary data directory
    with tempfile.TemporaryDirectory() as data_dir:
        lsp.DATA_DIR = Path(data_dir)

        # Initialize Database
        with lsp.app.app_context():
            db = sqlite3.connect(lsp.DATA_DIR / "database.db")
            with lsp.app.open_resource('sql/schema.sql', mode='r') as f:
                db.cursor().executescript(f.read())
            db.commit()
            db.close()

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

