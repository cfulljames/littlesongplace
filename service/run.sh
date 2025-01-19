#!/bin/bash
PORT=$1
export DATA_DIR=$2
export SECRET_KEY=$(< "$DATA_DIR/secret.key")
. venv/bin/activate
gunicorn -w 4 -b 127.0.0.1:$PORT 'main:app'

