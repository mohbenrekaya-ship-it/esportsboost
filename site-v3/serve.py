#!/usr/bin/env python3
"""Minimal static server for the V3 SPA. Serves this folder on port 4322.
Independent of the main site's serve.py (port 4321) — nothing here touches it."""
import functools
import http.server
import os
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4322

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("eSportsboost V3 preview on http://localhost:%d" % PORT)
    httpd.serve_forever()
