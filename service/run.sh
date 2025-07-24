#!/bin/bash
PORT=$1
export DATA_DIR=$2
export SECRET_KEY=$(< "$DATA_DIR/secret.key")
. venv/bin/activate
gunicorn --workers 8 --worker-class gthread --threads 16 -b 127.0.0.1:$PORT 'littlesongplace:app'

