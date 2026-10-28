"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI ``app`` in files under ``api/``.
We import the project's WSGI application from the repo root.

Note: there is no ``api/index.py`` in your project root, so this file is also
what makes ``/api/...`` URLs work without clashing with Django's routes.
"""

import os
import sys
from pathlib import Path

# Make the project root (parent of this file's folder) importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402

app = application
