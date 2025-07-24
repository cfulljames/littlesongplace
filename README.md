# little song place
Have feedback or bug reports?  Open an new issue on the
[issues page](https://github.com/cfulljames/littlesongplace/issues).

## Code Overview
This is a pretty simple [Flask](https://flask.palletsproject.com) app.  If
you've used Flask before, hopefully it feels pretty familiar.

Important Places:
- [`/src/littlesongplace`](/src/littlesongplace) - the main python code
- [`__init__.py`](/src/littlesongplace/__init__.py) - entry point; the main Flask() app instance
- [`/src/littlesongplace/templates`](/src/littlesongplace/templates) - HTML templates
- [`/src/littlesongplace/static`](/src/littlesongplace/static) - static files, including images, CSS, and Javascript
- [`/test`](/test) - tests, run with pytest

## Dependencies
This project has some dependencies that need to be installed manually to your system PATH:
- [Python 3.11](https://python.org)
- [ffmpeg](https://ffmpeg.org/)

## Environment Setup
In the cloned project directory, setup a Python environment and install the
necessary dependencies:
``` sh
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
. .venv/bin/activate

pip install -e .
pip install -r dev-requirements.txt
```

## Running
Run the app locally (accessible in a browser at localhost:5000):
``` sh
flask --app littlesongplace run --debug
```

## Testing
Run the tests with Pytest:
``` sh
pytest
```
