"""Production server: serves the built React SPA and the API under /api.

In dev, Vite serves the SPA and proxies /api -> the FastAPI backend. In the
container there is no Vite, so we mount the API app under /api (matching the
SPA's `/api` base) and serve the built static files at the root.

Run:  uvicorn server:server --host 0.0.0.0 --port 8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.main import app as api_app

server = FastAPI(title="Digital Receipts Analyzer")

# API first so /api/* is routed to the backend, everything else to the SPA.
server.mount("/api", api_app)

_dist = Path(__file__).resolve().parent / "web" / "dist"
if _dist.exists():
    server.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
