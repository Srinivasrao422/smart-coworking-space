"""
Vercel Serverless Function entry point for Smart Co-Working Space Management.
Exports a BaseHTTPRequestHandler 'handler' subclass for Vercel's Python runtime.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.server import CoworkingRequestHandler
from app.database import init_db, seed_db

# Initialize database on cold start
init_db()
seed_db()

class handler(CoworkingRequestHandler):
    """Vercel entrypoint handler."""
    pass
